package com.example.streetview

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.StringRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.Layers
import androidx.compose.material.icons.outlined.MyLocation
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Speed
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.colorResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.example.streetview.ui.theme.FieldBackground
import com.example.streetview.ui.theme.StreetViewTheme
import com.example.streetview.ui.theme.enableFieldEdgeToEdge
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private const val STATUS_SNAPSHOT = "dashboard.status"
private const val COMMAND_EXPECTED = "dashboard.command.expected"
private const val COMMAND_DEADLINE = "dashboard.command.deadline"
private const val PERMISSION_REQUEST = "dashboard.permission.request"
private const val POLL_INTERVAL_MS = 1_000L
private const val COMMAND_TIMEOUT_MS = 8_000L

private data class PendingCommand(val expectedRecording: Boolean, val deadlineMs: Long)

class MainActivity : ComponentActivity() {
    private val permissions = buildList {
        add(Manifest.permission.CAMERA)
        add(Manifest.permission.ACCESS_FINE_LOCATION)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }.toTypedArray()

    private var permissionRequestInFlight by mutableStateOf(false)
    private var lastStatus by mutableStateOf<Bundle?>(null)
    private var statusFresh by mutableStateOf(false)
    private var pendingCommand by mutableStateOf<PendingCommand?>(null)

    private val canControlCapture: Boolean
        get() = statusFresh && pendingCommand == null && !permissionRequestInFlight

    private val requestPermissionsLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
            permissionRequestInFlight = false
            val denied = result.filterValues { !it }.keys
            if (denied.isNotEmpty()) {
                Toast.makeText(
                    this,
                    getString(R.string.dashboard_permissions_denied, denied.joinToString()),
                    Toast.LENGTH_LONG
                ).show()
            } else {
                queryServiceStatus()
            }
        }

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != RecordingService.ACTION_STATUS_BROADCAST) return
            val snapshot = intent.extras ?: return
            if (!snapshot.containsKey(RecordingService.EXTRA_IS_RECORDING)) return
            val recording = snapshot.getBoolean(RecordingService.EXTRA_IS_RECORDING)
            // An old query or ticker response is not an acknowledgement of the new command.
            val pending = pendingCommand
            if (pending != null && pending.expectedRecording != recording) return

            lastStatus = snapshot
            statusFresh = lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
            if (pending != null) pendingCommand = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableFieldEdgeToEdge()
        lastStatus = savedInstanceState?.getBundle(STATUS_SNAPSHOT)
        permissionRequestInFlight = savedInstanceState?.getBoolean(PERMISSION_REQUEST) == true
        if (savedInstanceState?.containsKey(COMMAND_EXPECTED) == true) {
            pendingCommand = PendingCommand(
                savedInstanceState.getBoolean(COMMAND_EXPECTED),
                savedInstanceState.getLong(COMMAND_DEADLINE)
            )
        }

        ContextCompat.registerReceiver(
            this,
            statusReceiver,
            IntentFilter(RecordingService.ACTION_STATUS_BROADCAST),
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (isActive) {
                    if (pendingCommand?.let { SystemClock.elapsedRealtime() >= it.deadlineMs } == true) {
                        pendingCommand = null
                        statusFresh = false
                        notifyUser(R.string.dashboard_command_timeout)
                    }
                    queryServiceStatus()
                    delay(POLL_INTERVAL_MS)
                }
            }
        }

        val prefs = getSharedPreferences(QualityPrefs.PREFS, Context.MODE_PRIVATE)
        setContent {
            StreetViewTheme {
                var quality by remember { mutableStateOf(QualityPrefs.getQuality(prefs)) }
                val status = CaptureStatus.from(lastStatus)
                Dashboard(
                    status = status,
                    pending = pendingCommand,
                    canControlCapture = canControlCapture,
                    quality = quality,
                    onQualityChange = { value ->
                        QualityPrefs.setQuality(prefs, value)
                        quality = value
                        notifyUser(
                            if (value == QualityPrefs.QUALITY_OPTIMIZED) R.string.dashboard_quality_saved_optimized
                            else R.string.dashboard_quality_saved_standard
                        )
                    },
                    onPreview = {
                        if (canControlCapture && lastStatus?.getBoolean(RecordingService.EXTRA_IS_RECORDING) == false) {
                            startActivity(Intent(this, PositionActivity::class.java))
                        }
                    },
                    onToggleCapture = ::toggleCapture,
                    onOpenRecordings = { startActivity(Intent(this, RecordingsActivity::class.java)) }
                )
            }
        }

        if (savedInstanceState == null) ensurePermissions()
    }

    override fun onStop() {
        // Keep the last display snapshot, but require a fresh reply before enabling camera actions.
        statusFresh = false
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBundle(STATUS_SNAPSHOT, lastStatus)
        outState.putBoolean(PERMISSION_REQUEST, permissionRequestInFlight)
        pendingCommand?.let {
            outState.putBoolean(COMMAND_EXPECTED, it.expectedRecording)
            outState.putLong(COMMAND_DEADLINE, it.deadlineMs)
        }
    }

    override fun onDestroy() {
        unregisterReceiver(statusReceiver)
        super.onDestroy()
    }

    private fun hasPermissions() = permissions.all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun ensurePermissions() {
        if (!permissionRequestInFlight && !hasPermissions()) {
            permissionRequestInFlight = true
            requestPermissionsLauncher.launch(permissions)
        }
    }

    private fun toggleCapture() {
        if (!canControlCapture) return
        if (!hasPermissions()) {
            ensurePermissions()
            return
        }

        val recording = lastStatus?.getBoolean(RecordingService.EXTRA_IS_RECORDING) ?: return
        val command = PendingCommand(!recording, SystemClock.elapsedRealtime() + COMMAND_TIMEOUT_MS)
        pendingCommand = command
        try {
            if (command.expectedRecording) {
                ContextCompat.startForegroundService(this, serviceIntent(RecordingService.ACTION_START))
            } else {
                startService(serviceIntent(RecordingService.ACTION_STOP))
            }
            queryServiceStatus()
        } catch (_: IllegalStateException) {
            handleCommandFailure()
        } catch (_: SecurityException) {
            handleCommandFailure()
        }
    }

    private fun handleCommandFailure() {
        pendingCommand = null
        statusFresh = false
        notifyUser(R.string.dashboard_command_failed)
        queryServiceStatus()
    }

    private fun queryServiceStatus() {
        if (!lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return
        try {
            startService(serviceIntent(RecordingService.ACTION_QUERY_STATUS))
        } catch (_: IllegalStateException) {
            // Service starts can be rejected during foreground/background transitions.
        } catch (_: SecurityException) {
            // A later visible poll can retry if permissions changed.
        }
    }

    private fun serviceIntent(action: String) = Intent(this, RecordingService::class.java).setAction(action)

    private fun notifyUser(@StringRes message: Int) {
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }
}

private data class CaptureStatus(
    val recording: Boolean = false,
    val speedKmh: Float? = null,
    val accuracyM: Float? = null,
    val points: Int = 0,
    val elapsedMs: Long = 0L,
    val fileName: String = ""
) {
    companion object {
        fun from(extras: Bundle?): CaptureStatus {
            if (extras == null || !extras.getBoolean(RecordingService.EXTRA_IS_RECORDING)) {
                return CaptureStatus()
            }
            return CaptureStatus(
                recording = true,
                speedKmh = extras.availableGpsValue(
                    RecordingService.EXTRA_HAS_SPEED, RecordingService.EXTRA_SPEED
                )?.times(3.6f),
                accuracyM = extras.availableGpsValue(
                    RecordingService.EXTRA_HAS_ACCURACY, RecordingService.EXTRA_ACCURACY
                ),
                points = extras.getInt(RecordingService.EXTRA_POINTS),
                elapsedMs = extras.getLong(RecordingService.EXTRA_ELAPSED_MS),
                fileName = extras.getString(RecordingService.EXTRA_FILE_NAME).orEmpty()
            )
        }

        private fun Bundle.availableGpsValue(flag: String, key: String): Float? =
            if (getBoolean(flag)) getFloat(key, Float.NaN).takeIf { it.isFinite() && it >= 0f } else null
    }
}

@Composable
private fun Dashboard(
    status: CaptureStatus,
    pending: PendingCommand?,
    canControlCapture: Boolean,
    quality: String,
    onQualityChange: (String) -> Unit,
    onPreview: () -> Unit,
    onToggleCapture: () -> Unit,
    onOpenRecordings: () -> Unit
) {
    FieldBackground {
        BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding()) {
            val viewportHeight = maxHeight
            val headerGap = (viewportHeight * 0.13f).coerceIn(20.dp, 108.dp)
            Column(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .widthIn(max = 560.dp)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .heightIn(min = viewportHeight)
                    .padding(horizontal = 20.dp, vertical = 16.dp),
                verticalArrangement = Arrangement.SpaceBetween
            ) {
                Column {
                    DashboardHeader(
                        showBrand = canControlCapture && !status.recording,
                        quality = quality,
                        previewEnabled = canControlCapture && !status.recording,
                        onQualityChange = onQualityChange,
                        onPreview = onPreview
                    )
                    Spacer(Modifier.height(headerGap))
                    StatusCard(status, pending)
                    if (status.recording && pending == null) {
                        Text(
                            stringResource(R.string.dashboard_capture_in_progress),
                            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.secondary,
                            textAlign = TextAlign.Center
                        )
                    }
                }
                CaptureActions(
                    recording = status.recording,
                    pending = pending,
                    enabled = canControlCapture,
                    onToggleCapture = onToggleCapture,
                    onOpenRecordings = onOpenRecordings,
                    modifier = Modifier.padding(top = 24.dp)
                )
            }
        }
    }
}

@Composable
private fun DashboardHeader(
    showBrand: Boolean,
    quality: String,
    previewEnabled: Boolean,
    onQualityChange: (String) -> Unit,
    onPreview: () -> Unit
) {
    var settingsExpanded by rememberSaveable { mutableStateOf(false) }
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val scheme = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().heightIn(min = 64.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f)) {
            if (showBrand) {
                Column {
                    Text(
                        stringResource(R.string.app_name),
                        modifier = Modifier.semantics { heading() },
                        style = MaterialTheme.typography.displaySmall,
                        fontWeight = FontWeight.Bold,
                        color = scheme.onSurface
                    )
                    Text(
                        stringResource(R.string.dashboard_brand_caption),
                        style = MaterialTheme.typography.titleMedium,
                        color = scheme.secondary
                    )
                }
            }
        }
        Box {
            IconButton(
                onClick = { settingsExpanded = true },
                modifier = Modifier.size(48.dp),
                colors = IconButtonDefaults.iconButtonColors(
                    containerColor = scheme.secondaryContainer,
                    contentColor = scheme.onSurface
                )
            ) {
                Icon(Icons.Default.Settings, contentDescription = stringResource(R.string.dashboard_settings))
            }
            DropdownMenu(
                expanded = settingsExpanded,
                onDismissRequest = { settingsExpanded = false },
                modifier = Modifier.widthIn(max = 304.dp),
                shape = RoundedCornerShape(22.dp),
                containerColor = scheme.surface,
                shadowElevation = 12.dp
            ) {
                Text(
                    stringResource(R.string.dashboard_recording_quality),
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp).semantics { heading() },
                    style = MaterialTheme.typography.titleSmall,
                    color = scheme.onSurface
                )
                Column(Modifier.selectableGroup()) {
                    QualityOption(R.string.dashboard_quality_standard, quality == QualityPrefs.QUALITY_STANDARD) {
                        onQualityChange(QualityPrefs.QUALITY_STANDARD)
                        settingsExpanded = false
                    }
                    QualityOption(R.string.dashboard_quality_optimized, quality == QualityPrefs.QUALITY_OPTIMIZED) {
                        onQualityChange(QualityPrefs.QUALITY_OPTIMIZED)
                        settingsExpanded = false
                    }
                }
                HorizontalDivider(Modifier.padding(vertical = 4.dp), color = colorResource(R.color.field_border))
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.dashboard_camera_preview)) },
                    leadingIcon = { Icon(Icons.Outlined.Videocam, contentDescription = null,
                            tint = if (previewEnabled) scheme.primary else scheme.onSurfaceVariant) },
                    enabled = previewEnabled,
                    onClick = {
                        settingsExpanded = false
                        onPreview()
                    }
                )
                HorizontalDivider(Modifier.padding(vertical = 4.dp), color = colorResource(R.color.field_border))
                Text(
                    stringResource(R.string.dashboard_version, BuildConfig.VERSION_NAME),
                    modifier = Modifier.padding(start = 16.dp, top = 8.dp, end = 16.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = scheme.secondary
                )
                DropdownMenuItem(
                    text = {
                        Text(
                            stringResource(R.string.dashboard_credit),
                            style = MaterialTheme.typography.bodySmall,
                            color = scheme.primary
                        )
                    },
                    onClick = {
                        settingsExpanded = false
                        try {
                            uriHandler.openUri("https://github.com/markfishurupa-dot")
                        } catch (_: IllegalArgumentException) {
                            Toast.makeText(context, R.string.dashboard_credit_link_unavailable, Toast.LENGTH_SHORT).show()
                        }
                    }
                )
            }
        }
    }
}

@Composable
private fun QualityOption(@StringRes label: Int, selected: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .padding(horizontal = 8.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(if (selected) MaterialTheme.colorScheme.secondaryContainer else Color.Transparent)
            .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(stringResource(label), style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun StatusCard(status: CaptureStatus, pending: PendingCommand?) {
    val scheme = MaterialTheme.colorScheme
    val label = when (pending?.expectedRecording) {
        true -> R.string.dashboard_starting
        false -> R.string.dashboard_stopping
        null -> if (status.recording) R.string.dashboard_recording else R.string.dashboard_idle
    }
    val unavailable = stringResource(R.string.dashboard_unavailable_glyph)
    val seconds = status.elapsedMs.coerceAtLeast(0L) / 1_000L
    OutlinedCard(
        modifier = Modifier.fillMaxWidth().shadow(4.dp, RoundedCornerShape(24.dp), spotColor = scheme.onSurface.copy(alpha = 0.40f)),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.outlinedCardColors(containerColor = scheme.surface),
        border = BorderStroke(1.dp, colorResource(R.color.field_border))
    ) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val dot = when {
                    pending != null -> scheme.tertiary
                    status.recording -> colorResource(R.color.field_success)
                    else -> scheme.secondary
                }
                Box(Modifier.size(16.dp).background(dot, CircleShape))
                Column {
                    Text(
                        stringResource(label),
                        modifier = Modifier.semantics {
                            heading()
                            liveRegion = LiveRegionMode.Polite
                        },
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold
                    )
                    if (status.fileName.isNotBlank()) {
                        Text(status.fileName, style = MaterialTheme.typography.bodyMedium, color = scheme.secondary)
                    }
                }
            }
            Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric(
                    Icons.Outlined.Speed,
                    R.string.dashboard_speed,
                    status.speedKmh?.let { stringResource(R.string.dashboard_speed_value, it) } ?: unavailable,
                    Modifier.weight(1f),
                    unavailable = status.speedKmh == null
                )
                VerticalDivider(color = scheme.outlineVariant)
                Metric(
                    Icons.Outlined.MyLocation,
                    R.string.dashboard_accuracy,
                    status.accuracyM?.let { stringResource(R.string.dashboard_accuracy_value, it) } ?: unavailable,
                    Modifier.weight(1f),
                    unavailable = status.accuracyM == null
                )
            }
            HorizontalDivider(color = scheme.outlineVariant)
            Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Metric(
                    Icons.Outlined.Layers,
                    R.string.dashboard_points,
                    stringResource(R.string.dashboard_points_value, status.points),
                    Modifier.weight(1f)
                )
                VerticalDivider(color = scheme.outlineVariant)
                Metric(
                    Icons.Outlined.Schedule,
                    R.string.dashboard_elapsed,
                    stringResource(R.string.dashboard_elapsed_value, seconds / 60, seconds % 60),
                    Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun Metric(
    icon: ImageVector,
    @StringRes label: Int,
    value: String,
    modifier: Modifier,
    unavailable: Boolean = false
) {
    val scheme = MaterialTheme.colorScheme
    val unavailableText = stringResource(R.string.dashboard_unavailable_description)
    Row(
        modifier = modifier.semantics(mergeDescendants = true) {},
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, contentDescription = null, tint = scheme.primary, modifier = Modifier.size(24.dp))
        Column(Modifier.weight(1f)) {
            Text(stringResource(label), style = MaterialTheme.typography.bodySmall, color = scheme.secondary)
            Text(
                value,
                modifier = if (unavailable) Modifier.clearAndSetSemantics { contentDescription = unavailableText }
                else Modifier,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = scheme.onSurface
            )
        }
    }
}

private val ActionShape = RoundedCornerShape(24.dp)

@Composable
private fun CaptureActions(
    recording: Boolean,
    pending: PendingCommand?,
    enabled: Boolean,
    onToggleCapture: () -> Unit,
    onOpenRecordings: () -> Unit,
    modifier: Modifier = Modifier
) {
    val navy = colorResource(R.color.field_navy)
    val scheme = MaterialTheme.colorScheme
    val actionModifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
    val startOrStop = when (pending?.expectedRecording) {
        true -> R.string.dashboard_starting
        false -> R.string.dashboard_stopping
        null -> if (recording) R.string.dashboard_stop else R.string.dashboard_start
    }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        DashboardAction(
            label = startOrStop,
            icon = if (recording) Icons.Default.Stop else Icons.Default.PlayArrow,
            onClick = onToggleCapture,
            modifier = actionModifier,
            navy = navy,
            orange = !recording,
            enabled = enabled
        )
        if (!recording && pending == null) {
            Text(
                stringResource(R.string.dashboard_capture_hint),
                modifier = Modifier.fillMaxWidth(),
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Center,
                color = scheme.secondary
            )
        }
        if (recording) {
            DashboardAction(
                R.string.dashboard_open_recordings, Icons.Default.FolderOpen,
                onOpenRecordings, actionModifier, navy, orange = true
            )
        } else {
            OutlinedButton(
                onClick = onOpenRecordings,
                modifier = actionModifier,
                shape = ActionShape,
                border = BorderStroke(1.dp, scheme.primary),
                colors = ButtonDefaults.outlinedButtonColors(containerColor = scheme.secondaryContainer.copy(alpha = 0.45f), contentColor = scheme.primary)
            ) {
                ActionLabel(Icons.Default.FolderOpen, R.string.dashboard_open_recordings)
            }
        }
    }
}

@Composable
private fun DashboardAction(
    @StringRes label: Int,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier,
    navy: Color,
    orange: Boolean,
    enabled: Boolean = true
) {
    Button(
        onClick = onClick,
        modifier = modifier,
        enabled = enabled,
        shape = ActionShape,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (orange) colorResource(R.color.field_orange) else navy,
            contentColor = if (orange) navy else Color.White,
            disabledContainerColor = MaterialTheme.colorScheme.secondaryContainer,
            disabledContentColor = MaterialTheme.colorScheme.onSurface
        )
    ) {
        ActionLabel(icon, label, iconTint = if (orange && enabled) Color.White else LocalContentColor.current)
    }
}

@Composable
private fun ActionLabel(
    icon: ImageVector,
    @StringRes label: Int,
    iconTint: Color = LocalContentColor.current
) {
    Icon(icon, contentDescription = null, modifier = Modifier.size(22.dp), tint = iconTint)
    Spacer(Modifier.width(8.dp))
    Text(stringResource(label), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
}

object QualityPrefs {
    const val PREFS = "streetview_prefs"
    private const val KEY_QUALITY = "quality_mode"

    const val QUALITY_STANDARD = "standard"
    const val QUALITY_OPTIMIZED = "optimized"

    fun getQuality(prefs: SharedPreferences): String =
        prefs.getString(KEY_QUALITY, QUALITY_STANDARD) ?: QUALITY_STANDARD

    fun setQuality(prefs: SharedPreferences, value: String) {
        prefs.edit().putString(KEY_QUALITY, value).apply()
    }
}
