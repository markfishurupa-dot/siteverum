package com.example.streetview

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.SurfaceTexture
import android.hardware.camera2.*
import android.os.Bundle
import android.util.Size
import android.view.Surface
import android.view.TextureView
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface as ComposeSurface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.example.streetview.ui.theme.StreetViewTheme

class PositionActivity : ComponentActivity() {

    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var cameraManager: CameraManager? = null
    private var cameraId: String? = null
    private var previewSize: Size = Size(1280, 720)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        cameraManager = getSystemService(CameraManager::class.java)
        cameraId = chooseBackCameraId(cameraManager!!)

        setContent {
            StreetViewTheme {
                val bg = Color(0xFFF6F7F9)
                val darkBlue = Color(0xFF0B2B3A)

                ComposeSurface(modifier = Modifier.fillMaxSize(), color = bg) {
                    Box(modifier = Modifier.fillMaxSize()) {

                        var textureViewRef by remember { mutableStateOf<TextureView?>(null) }

                        AndroidView(
                            modifier = Modifier.fillMaxSize(),
                            factory = { ctx ->
                                TextureView(ctx).also { tv ->
                                    textureViewRef = tv
                                    tv.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                                        override fun onSurfaceTextureAvailable(st: SurfaceTexture, w: Int, h: Int) {
                                            startPreview(tv)
                                        }
                                        override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, w: Int, h: Int) {}
                                        override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean {
                                            stopPreview()
                                            return true
                                        }
                                        override fun onSurfaceTextureUpdated(st: SurfaceTexture) {}
                                    }
                                }
                            }
                        )

                        // Simple alignment overlay text
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .statusBarsPadding()
                                .padding(16.dp),
                            horizontalAlignment = Alignment.Start
                        ) {
                            Text(
                                text = "Camera alignment",
                                style = MaterialTheme.typography.headlineMedium,
                                color = darkBlue
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                text = "Aim the camera to capture the street clearly.\nTip: keep horizon ~upper third.",
                                color = darkBlue
                            )
                        }

                        // Bottom hint
                        Text(
                            text = "Press Back when aligned ✅",
                            modifier = Modifier
                                .align(Alignment.BottomCenter)
                                .navigationBarsPadding()
                                .padding(16.dp),
                            color = darkBlue
                        )
                    }
                }
            }
        }
    }

    private fun startPreview(textureView: TextureView) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            // Camera permission is already requested in MainActivity, so usually OK.
            return
        }

        val cm = cameraManager ?: return
        val id = cameraId ?: return

        cm.openCamera(id, object : CameraDevice.StateCallback() {
            override fun onOpened(device: CameraDevice) {
                cameraDevice = device
                createPreviewSession(textureView, device)
            }

            override fun onDisconnected(device: CameraDevice) {
                device.close()
                cameraDevice = null
            }

            override fun onError(device: CameraDevice, error: Int) {
                device.close()
                cameraDevice = null
            }
        }, null)
    }

    private fun createPreviewSession(textureView: TextureView, device: CameraDevice) {
        val st = textureView.surfaceTexture ?: return
        st.setDefaultBufferSize(previewSize.width, previewSize.height)
        val surface = Surface(st)

        val request = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
            addTarget(surface)
            set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
        }.build()

        device.createCaptureSession(listOf(surface), object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(session: CameraCaptureSession) {
                captureSession = session
                try {
                    session.setRepeatingRequest(request, null, null)
                } catch (_: Exception) {}
            }

            override fun onConfigureFailed(session: CameraCaptureSession) {}
        }, null)
    }

    private fun stopPreview() {
        try { captureSession?.close() } catch (_: Exception) {}
        captureSession = null
        try { cameraDevice?.close() } catch (_: Exception) {}
        cameraDevice = null
    }

    override fun onStop() {
        super.onStop()
        stopPreview()
    }

    private fun chooseBackCameraId(cm: CameraManager): String {
        for (id in cm.cameraIdList) {
            val chars = cm.getCameraCharacteristics(id)
            val facing = chars.get(CameraCharacteristics.LENS_FACING)
            if (facing == CameraCharacteristics.LENS_FACING_BACK) return id
        }
        return cm.cameraIdList.first()
    }
}
