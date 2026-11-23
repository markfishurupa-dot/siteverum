package com.example.streetview

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraAccessException
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CameraMetadata
import android.hardware.camera2.CaptureRequest
import android.hardware.display.DisplayManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.util.Size
import android.view.Gravity
import android.view.Surface
import android.view.TextureView
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.material3.Surface as ComposeSurface
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.example.streetview.ui.theme.FieldBackground
import com.example.streetview.ui.theme.StreetViewTheme
import com.example.streetview.ui.theme.enableFieldEdgeToEdge
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min

class PositionActivity : ComponentActivity() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val cameraManager by lazy { getSystemService(CameraManager::class.java) }
    private val displayManager by lazy { getSystemService(DisplayManager::class.java) }
    private var viewfinder: AlignmentViewfinder? = null
    private var resumed = false
    private var previewState by mutableStateOf(PreviewState.Starting)

    // All lifecycle, texture and camera state is confined to the main looper. Keep an
    // attempt until onClosed, even if its open callback is still pending at teardown.
    private var attempt: PreviewAttempt? = null

    private val displayListener = object : DisplayManager.DisplayListener {
        override fun onDisplayAdded(displayId: Int) = Unit
        override fun onDisplayRemoved(displayId: Int) = Unit
        override fun onDisplayChanged(displayId: Int) {
            viewfinder?.takeIf { it.display?.displayId == displayId }?.updateTransform()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableFieldEdgeToEdge()
        setContent {
            StreetViewTheme {
                FieldBackground {
                    AlignmentScreen(
                        state = previewState,
                        onBack = { onBackPressedDispatcher.onBackPressed() },
                        onRetry = ::retryPreview,
                        preview = { modifier -> CameraView(modifier) }
                    )
                }
            }
        }
    }

    @Composable
    private fun CameraView(modifier: Modifier) {
        AndroidView(
            modifier = modifier,
            factory = { context -> AlignmentViewfinder(context).also { viewfinder = it } },
            onReset = null,
            onRelease = { view ->
                if (viewfinder === view) {
                    viewfinder = null
                    if (resumed) previewState = PreviewState.Starting
                    stopPreview()
                }
                view.texture.surfaceTextureListener = null
            }
        )
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        displayManager?.registerDisplayListener(displayListener, mainHandler)
        viewfinder?.updateTransform()
        retryPreview()
    }

    override fun onPause() {
        resumed = false
        displayManager?.unregisterDisplayListener(displayListener)
        stopPreview()
        previewState = PreviewState.Starting
        super.onPause()
    }

    private fun retryPreview() {
        previewState = PreviewState.Starting
        maybeStartPreview()
    }

    private fun maybeStartPreview() {
        if (!resumed || isFinishing || attempt != null || previewState != PreviewState.Starting) return
        val view = viewfinder ?: return
        if (!view.isAttachedToWindow || view.width <= 0 || view.height <= 0) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            previewState = PreviewState.PermissionNeeded
            return
        }
        val manager = cameraManager ?: run {
            previewState = PreviewState.Unavailable
            return
        }

        cameraOperation(onFailure = { error ->
            // A synchronous open failure has no closing callback.
            attempt = null
            showFailure(error)
        }) {
            val spec = view.spec ?: choosePreview(manager, view)?.also(view::installPreview)
            if (spec == null) {
                previewState = PreviewState.Unavailable
                return@cameraOperation
            }
            val texture = view.texture.surfaceTexture?.takeIf { view.texture.isAvailable }
                ?: return@cameraOperation
            val opening = PreviewAttempt(view, texture, spec)
            attempt = opening
            manager.openCamera(spec.id, cameraCallback(opening), mainHandler)
        }
    }

    private fun cameraCallback(opening: PreviewAttempt) = object : CameraDevice.StateCallback() {
        override fun onOpened(device: CameraDevice) {
            if (!isCurrent(opening)) {
                device.close()
                return
            }
            opening.device = device
            createPreviewSession(opening, device)
        }

        override fun onDisconnected(device: CameraDevice) = deviceLost(device)

        override fun onError(device: CameraDevice, error: Int) {
            if (isCurrent(opening)) Log.w(TAG, "Camera device error: $error")
            deviceLost(device)
        }

        private fun deviceLost(device: CameraDevice) {
            if (isCurrent(opening)) {
                opening.device = device
                showFailure(null)
                stopPreview()
            } else {
                device.close()
            }
        }

        override fun onClosed(device: CameraDevice) {
            if (attempt !== opening) return
            // An unexpected close must also release anything left in this attempt.
            opening.device = null
            if (!opening.retired) {
                if (isCurrent(opening)) showFailure(null)
                stopPreview()
            }
            opening.output?.release()
            opening.output = null
            attempt = null
            maybeStartPreview()
        }
    }

    @Suppress("DEPRECATION") // The Handler overload also supports API 26 and 27.
    private fun createPreviewSession(opening: PreviewAttempt, device: CameraDevice) {
        cameraOperation(onFailure = { failAttempt(opening, it) }) {
            val size = opening.spec.size
            opening.texture.setDefaultBufferSize(size.width, size.height)
            opening.view.updateTransform()
            val output = Surface(opening.texture)
            opening.output = output
            val request = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                addTarget(output)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                    opening.spec.characteristics.get(CameraCharacteristics.SCALER_AVAILABLE_ROTATE_AND_CROP_MODES)
                        ?.contains(CameraMetadata.SCALER_ROTATE_AND_CROP_NONE) == true
                ) {
                    // The viewfinder handles rotation and crop, not the camera HAL.
                    set(CaptureRequest.SCALER_ROTATE_AND_CROP, CameraMetadata.SCALER_ROTATE_AND_CROP_NONE)
                }
            }.build()
            device.createCaptureSession(listOf(output), object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    if (!isCurrent(opening)) {
                        session.close()
                        return
                    }
                    opening.session = session
                    cameraOperation(onFailure = { failAttempt(opening, it) }) {
                        session.setRepeatingRequest(request, null, mainHandler)
                        opening.repeating = true
                    }
                }

                override fun onConfigureFailed(session: CameraCaptureSession) {
                    session.close()
                    failAttempt(opening)
                }
            }, mainHandler)
        }
    }

    private fun isCurrent(opening: PreviewAttempt): Boolean =
        attempt === opening && !opening.retired && resumed && !isFinishing &&
            viewfinder === opening.view && opening.view.texture.surfaceTexture === opening.texture

    private fun failAttempt(opening: PreviewAttempt, error: Exception? = null) {
        if (!isCurrent(opening)) return
        showFailure(error)
        stopPreview()
    }

    private fun showFailure(error: Exception?) {
        if (error != null) Log.w(TAG, "Unable to start alignment preview", error)
        previewState = if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) !=
            PackageManager.PERMISSION_GRANTED
        ) PreviewState.PermissionNeeded else PreviewState.Unavailable
    }

    private fun stopPreview() {
        val closing = attempt ?: return
        if (closing.retired) return
        closing.retired = true
        closing.session?.close()
        closing.session = null
        // Keep the wrapper alive while Camera2 finishes closing the device. Any
        // late session callback sees retired and closes its session without using it.
        closing.device?.close()
        closing.device = null
    }

    private fun choosePreview(manager: CameraManager, view: AlignmentViewfinder): PreviewSpec? {
        // Prefer a rear camera, but retain support for devices with only a front or external camera.
        val specs = manager.cameraIdList.mapNotNull { id ->
            val characteristics = manager.getCameraCharacteristics(id)
            val sizes = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                ?.getOutputSizes(SurfaceTexture::class.java).orEmpty()
            if (sizes.isEmpty()) return@mapNotNull null
            val budget = sizes.filter { max(it.width, it.height) <= 1920 && min(it.width, it.height) <= 1080 }
                .ifEmpty { listOf(sizes.minBy { it.width.toLong() * it.height }) }
            val sensor = characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0
            val swap = (sensor - view.rotationDegrees()) % 180 != 0
            val viewAspect = view.width.toDouble() / view.height
            val size = budget.minWith(compareBy<Size> {
                val width = if (swap) it.height else it.width
                val height = if (swap) it.width else it.height
                // Prefer a buffer that won't need upscaling; among those, crop the least.
                max(1.0, max(view.width.toDouble() / width, view.height.toDouble() / height))
            }.thenBy {
                val aspect = if (swap) it.height.toDouble() / it.width else it.width.toDouble() / it.height
                abs(ln(aspect / viewAspect))
            }.thenBy { it.width.toLong() * it.height })
            PreviewSpec(id, characteristics, size)
        }
        return specs.firstOrNull {
            it.characteristics.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: specs.firstOrNull()
    }

    private inline fun cameraOperation(onFailure: (Exception) -> Unit, block: () -> Unit) {
        try {
            block()
        } catch (error: CameraAccessException) {
            onFailure(error)
        } catch (error: SecurityException) {
            onFailure(error)
        } catch (error: IllegalStateException) {
            onFailure(error)
        } catch (error: IllegalArgumentException) {
            onFailure(error)
        }
    }

    private inner class AlignmentViewfinder(context: Context) : FrameLayout(context), TextureView.SurfaceTextureListener {
        val texture = TextureView(context).apply {
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
            surfaceTextureListener = this@AlignmentViewfinder
        }
        var spec: PreviewSpec? = null
            private set

        init {
            outlineProvider = ViewOutlineProvider.BOUNDS
            clipToOutline = true
        }

        fun installPreview(config: PreviewSpec) {
            spec = config
            // Keep the child at the supported buffer size so a window resize won't reset
            // SurfaceTexture's default buffer size to arbitrary view dimensions.
            addView(texture, LayoutParams(config.size.width, config.size.height, Gravity.CENTER))
            updateTransform()
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            post { if (viewfinder === this) maybeStartPreview() }
        }

        override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
            super.onSizeChanged(w, h, oldw, oldh)
            updateTransform()
            // Initial size discovery can add the texture child; don't do it during layout.
            post { if (viewfinder === this) maybeStartPreview() }
        }

        fun rotationDegrees(): Int = when (display?.rotation) {
            Surface.ROTATION_90 -> 90
            Surface.ROTATION_180 -> 180
            Surface.ROTATION_270 -> 270
            else -> 0
        }

        fun updateTransform() {
            val config = spec ?: return
            if (width <= 0 || height <= 0) return
            val size = config.size
            val sensor = config.characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0
            val displayDegrees = rotationDegrees()
            // TextureView receives buffers already rotated into the display's natural orientation.
            // Undo its stretch, then apply only the missing display rotation and a uniform fill.
            val sourceWidth = if (sensor % 180 == 0) size.width else size.height
            val sourceHeight = if (sensor % 180 == 0) size.height else size.width
            val swapForDisplay = displayDegrees % 180 != 0
            val rotatedWidth = if (swapForDisplay) sourceHeight else sourceWidth
            val rotatedHeight = if (swapForDisplay) sourceWidth else sourceHeight
            val fill = max(width.toFloat() / rotatedWidth, height.toFloat() / rotatedHeight)
            texture.scaleX = fill * sourceWidth / size.width
            texture.scaleY = fill * sourceHeight / size.height
            texture.rotation = -displayDegrees.toFloat()
        }

        override fun onSurfaceTextureAvailable(surface: SurfaceTexture, width: Int, height: Int) {
            if (viewfinder === this) maybeStartPreview()
        }

        override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, width: Int, height: Int) {
            updateTransform()
        }

        override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean {
            if (attempt?.texture === surface) stopPreview()
            if (viewfinder === this && previewState == PreviewState.Live) previewState = PreviewState.Starting
            return true // TextureView owns the SurfaceTexture; the attempt owns only its Surface wrapper.
        }

        override fun onSurfaceTextureUpdated(surface: SurfaceTexture) {
            if (previewState != PreviewState.Starting) return
            val opening = attempt ?: return
            if (opening.texture === surface && opening.repeating && isCurrent(opening)) {
                previewState = PreviewState.Live
            }
        }
    }

    private data class PreviewSpec(val id: String, val characteristics: CameraCharacteristics, val size: Size)

    private class PreviewAttempt(val view: AlignmentViewfinder, val texture: SurfaceTexture, val spec: PreviewSpec) {
        var device: CameraDevice? = null
        var session: CameraCaptureSession? = null
        var output: Surface? = null
        var repeating = false
        var retired = false
    }

    private companion object {
        const val TAG = "PositionActivity"
    }
}

private enum class PreviewState { Starting, Live, PermissionNeeded, Unavailable }

@Composable
private fun AlignmentScreen(
    state: PreviewState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    preview: @Composable (Modifier) -> Unit
) {
    BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()) {
        val landscape = maxWidth > maxHeight
        val colors = MaterialTheme.colorScheme
        if (landscape) {
            Box(Modifier.fillMaxSize()) {
                preview(Modifier.matchParentSize())
                if (state == PreviewState.Live) HorizonGuide(Modifier.matchParentSize())
                else Spacer(Modifier.matchParentSize().background(colors.surfaceContainerLow))

                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(Modifier.weight(1f)) { AlignmentHeader(onBack, compact = true) }
                    OrientationBadge(landscape = true)
                }
                AlignmentHint(
                    state, onRetry, compact = true,
                    modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp).widthIn(max = 360.dp)
                )
            }
        } else {
            Column(
                Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    AlignmentHeader(onBack, compact = false, modifier = Modifier.fillMaxWidth())
                    Text(
                        stringResource(R.string.alignment_aim),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.onSurface
                    )
                    Text(
                        stringResource(R.string.alignment_tip),
                        style = MaterialTheme.typography.bodyMedium,
                        color = colors.onSurfaceVariant
                    )
                }
                Box(Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(20.dp))) {
                    preview(Modifier.matchParentSize())
                    if (state == PreviewState.Live) HorizonGuide(Modifier.matchParentSize())
                    else Spacer(Modifier.matchParentSize().background(colors.surfaceContainerLow))
                    Box(Modifier.align(Alignment.TopEnd).padding(12.dp)) { OrientationBadge(landscape = false) }
                }
                AlignmentHint(state, onRetry, compact = false, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun AlignmentHeader(onBack: () -> Unit, compact: Boolean, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    ComposeSurface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = if (compact) colors.surface.copy(alpha = 0.94f) else Color.Transparent,
        contentColor = colors.onSurface
    ) {
        Row(
            Modifier.padding(start = 2.dp, end = 14.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.alignment_back))
            }
            Column {
                Text(
                    stringResource(R.string.alignment_title),
                    modifier = Modifier.semantics { heading() },
                    style = if (compact) MaterialTheme.typography.titleMedium else MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                if (compact) {
                    Text(
                        stringResource(R.string.alignment_tip),
                        style = MaterialTheme.typography.bodySmall,
                        color = colors.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun OrientationBadge(landscape: Boolean) {
    val colors = MaterialTheme.colorScheme
    ComposeSurface(
        shape = RoundedCornerShape(percent = 50),
        color = colors.secondaryContainer.copy(alpha = 0.94f),
        contentColor = colors.onSecondaryContainer
    ) {
        Text(
            stringResource(if (landscape) R.string.alignment_landscape else R.string.alignment_portrait),
            Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            style = MaterialTheme.typography.labelMedium
        )
    }
}

@Composable
private fun AlignmentHint(state: PreviewState, onRetry: () -> Unit, compact: Boolean, modifier: Modifier) {
    val colors = MaterialTheme.colorScheme
    ComposeSurface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = colors.surfaceContainerHigh.copy(alpha = if (compact) 0.92f else 1f),
        contentColor = colors.onSurface
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = if (compact) 8.dp else 12.dp),
            horizontalAlignment = if (state == PreviewState.Live) Alignment.CenterHorizontally else Alignment.Start
        ) {
            Text(
                stringResource(when (state) {
                    PreviewState.Starting -> R.string.alignment_opening
                    PreviewState.Live -> R.string.alignment_back_when_aligned
                    PreviewState.PermissionNeeded -> R.string.alignment_permission
                    PreviewState.Unavailable -> R.string.alignment_unavailable
                }),
                modifier = if (state == PreviewState.Live) Modifier else Modifier.semantics {
                    liveRegion = LiveRegionMode.Polite
                },
                style = if (compact) MaterialTheme.typography.bodySmall else MaterialTheme.typography.bodyMedium,
                color = colors.onSurfaceVariant,
                textAlign = if (state == PreviewState.Live) TextAlign.Center else TextAlign.Start
            )
            if (state == PreviewState.Unavailable) {
                TextButton(onClick = onRetry) { Text(stringResource(R.string.alignment_retry)) }
            }
        }
    }
}

private const val HORIZON_GUIDE_FRACTION = 0.55f

@Composable
private fun HorizonGuide(modifier: Modifier) {
    val colors = MaterialTheme.colorScheme
    BoxWithConstraints(modifier) {
        val guideOffset = maxHeight * (HORIZON_GUIDE_FRACTION - 0.5f)
        Canvas(Modifier.matchParentSize()) {
            val y = size.height * HORIZON_GUIDE_FRACTION
            val start = Offset(0f, y)
            val end = Offset(size.width, y)
            drawLine(Color.White, start, end, strokeWidth = 5.dp.toPx())
            drawLine(colors.primary, start, end, strokeWidth = 3.dp.toPx())
        }
        Box(
            modifier = Modifier.matchParentSize().offset(y = guideOffset).padding(horizontal = 8.dp),
            contentAlignment = Alignment.Center
        ) {
            ComposeSurface(
                shape = RoundedCornerShape(20.dp),
                color = colors.surface,
                contentColor = colors.primary,
                border = BorderStroke(1.dp, colors.primary)
            ) {
                Text(
                    stringResource(R.string.alignment_horizon),
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.labelLarge,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}
