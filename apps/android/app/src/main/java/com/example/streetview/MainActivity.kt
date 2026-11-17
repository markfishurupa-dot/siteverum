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
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.example.streetview.ui.theme.StreetViewTheme
import kotlinx.coroutines.delay
import kotlin.math.max

class MainActivity : ComponentActivity() {

    private val permissions = buildList {
        add(Manifest.permission.CAMERA)
        add(Manifest.permission.ACCESS_FINE_LOCATION)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }.toTypedArray()

    private val requestPermissionsLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
            val denied = result.filterValues { !it }.keys
            if (denied.isNotEmpty()) {
                Toast.makeText(this, "Permissions denied: ${denied.joinToString()}", Toast.LENGTH_LONG).show()
            } else {
                queryServiceStatus()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = getSharedPreferences(QualityPrefs.PREFS, Context.MODE_PRIVATE)

        setContent {
            StreetViewTheme {

                var isRecording by remember { mutableStateOf(false) }
                var speedMps by remember { mutableFloatStateOf(0f) }
                var accuracyM by remember { mutableFloatStateOf(0f) }
                var points by remember { mutableIntStateOf(0) }
                var elapsedMs by remember { mutableLongStateOf(0L) }
                var fileName by remember { mutableStateOf("") }

                var menuExpanded by remember { mutableStateOf(false) }
                var quality by remember { mutableStateOf(QualityPrefs.getQuality(prefs)) }

                // Receiver for service status
                DisposableEffect(Unit) {
                    val receiver = object : BroadcastReceiver() {
                        override fun onReceive(context: Context, intent: Intent) {
                            if (intent.action != RecordingService.ACTION_STATUS_BROADCAST) return
                            isRecording = intent.getBooleanExtra(RecordingService.EXTRA_IS_RECORDING, false)
                            speedMps = intent.getFloatExtra(RecordingService.EXTRA_SPEED, 0f)
                            accuracyM = intent.getFloatExtra(RecordingService.EXTRA_ACCURACY, 0f)
                            points = intent.getIntExtra(RecordingService.EXTRA_POINTS, 0)
                            elapsedMs = intent.getLongExtra(RecordingService.EXTRA_ELAPSED_MS, 0L)
                            fileName = intent.getStringExtra(RecordingService.EXTRA_FILE_NAME) ?: ""
                        }
                    }

                    val filter = IntentFilter(RecordingService.ACTION_STATUS_BROADCAST)
                    ContextCompat.registerReceiver(
                        this@MainActivity,
                        receiver,
                        filter,
                        ContextCompat.RECEIVER_NOT_EXPORTED
                    )

                    onDispose {
                        try { unregisterReceiver(receiver) } catch (_: Exception) {}
                    }
                }

                LaunchedEffect(Unit) {
                    ensurePermissions()
                    queryServiceStatus()
                }

                // Poll to keep UI in sync
                LaunchedEffect(Unit) {
                    while (true) {
                        queryServiceStatus()
                        delay(1000)
                    }
                }

                val orange = Color(0xFFFF7A00)
                val darkBlue = Color(0xFF0B2B3A)
                val bg = Color(0xFFF6F7F9)

                Surface(modifier = Modifier.fillMaxSize(), color = bg) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .statusBarsPadding()
                            .navigationBarsPadding()
                            .padding(16.dp),
                        verticalArrangement = Arrangement.SpaceBetween
                    ) {

                        // Header row: title + settings icon aligned
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "StreetView",
                                style = MaterialTheme.typography.headlineMedium,
                                fontWeight = FontWeight.Bold,
                                color = darkBlue
                            )

                            Spacer(Modifier.weight(1f))

                            Box {
                                IconButton(onClick = { menuExpanded = true }) {
                                    Icon(
                                        imageVector = Icons.Filled.Settings,
                                        contentDescription = "Settings",
                                        tint = darkBlue
                                    )
                                }

                                DropdownMenu(
                                    expanded = menuExpanded,
                                    onDismissRequest = { menuExpanded = false }
                                ) {
                                    // Quality header (disabled item)
                                    DropdownMenuItem(
                                        text = { Text("Recording quality") },
                                        onClick = { },
                                        enabled = false
                                    )

                                    DropdownMenuItem(
                                        text = { Text(if (quality == QualityPrefs.QUALITY_STANDARD) "✅ Standard" else "Standard") },
                                        onClick = {
                                            quality = QualityPrefs.QUALITY_STANDARD
                                            QualityPrefs.setQuality(prefs, quality)
                                            menuExpanded = false
                                            Toast.makeText(this@MainActivity, "Quality: Standard", Toast.LENGTH_SHORT).show()
                                        }
                                    )

                                    DropdownMenuItem(
                                        text = { Text(if (quality == QualityPrefs.QUALITY_OPTIMIZED) "✅ Optimized (smaller files)" else "Optimized (smaller files)") },
                                        onClick = {
                                            quality = QualityPrefs.QUALITY_OPTIMIZED
                                            QualityPrefs.setQuality(prefs, quality)
                                            menuExpanded = false
                                            Toast.makeText(this@MainActivity, "Quality: Optimized", Toast.LENGTH_SHORT).show()
                                        }
                                    )

                                    Divider()

                                    DropdownMenuItem(
                                        text = { Text("Camera alignment (preview)") },
                                        onClick = {
                                            menuExpanded = false
                                            startActivity(Intent(this@MainActivity, PositionActivity::class.java))
                                        }
                                    )

                                    Divider()

                                    DropdownMenuItem(
                                        text = { Text("Developed by Mark URUPA 2025", color = Color.Gray) },
                                        onClick = { },
                                        enabled = false
                                    )
                                }
                            }
                        }

                        // Status card
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(16.dp)
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {

                                Text(
                                    text = if (isRecording) "Recording ✅" else "Idle",
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.Bold,
                                    color = darkBlue
                                )

                                if (fileName.isNotBlank()) {
                                    Text(
                                        text = fileName,
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = darkBlue,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }

                                val kmh = speedMps * 3.6f
                                Text(
                                    text =
                                        "Speed: ${"%.1f".format(kmh)} km/h  |  " +
                                                "Acc: ${"%.1f".format(accuracyM)} m  |  " +
                                                "Points: $points  |  " +
                                                "Time: ${formatElapsed(elapsedMs)}",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = darkBlue,
                                    modifier = Modifier.padding(top = 8.dp)
                                )
                            }
                        }

                        // Bottom buttons
                        Column(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            val mainText = if (isRecording) "Stop" else "Start"
                            val mainColor = if (isRecording) darkBlue else orange

                            Button(
                                onClick = {
                                    ensurePermissionsThen {
                                        val action =
                                            if (isRecording) RecordingService.ACTION_STOP
                                            else RecordingService.ACTION_START

                                        val i = Intent(this@MainActivity, RecordingService::class.java).apply {
                                            this.action = action
                                        }

                                        if (action == RecordingService.ACTION_START) {
                                            ContextCompat.startForegroundService(this@MainActivity, i)
                                        } else {
                                            startService(i)
                                        }

                                        queryServiceStatus()
                                    }
                                },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(60.dp),
                                shape = RoundedCornerShape(22.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = mainColor)
                            ) {
                                Text(mainText, color = Color.White, fontWeight = FontWeight.Bold)
                            }

                            Spacer(Modifier.height(12.dp))

                            Button(
                                onClick = { startActivity(Intent(this@MainActivity, RecordingsActivity::class.java)) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(60.dp),
                                shape = RoundedCornerShape(22.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = orange)
                            ) {
                                Text("Open Recordings", color = Color.White, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }
    }

    private fun ensurePermissions() {
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) requestPermissionsLauncher.launch(permissions)
    }

    private fun ensurePermissionsThen(block: () -> Unit) {
        val granted = permissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
        if (granted) block() else ensurePermissions()
    }

    private fun queryServiceStatus() {
        startService(Intent(this, RecordingService::class.java).apply {
            action = RecordingService.ACTION_QUERY_STATUS
        })
    }

    private fun formatElapsed(ms: Long): String {
        val totalSec = max(0L, ms) / 1000L
        val m = totalSec / 60L
        val s = totalSec % 60L
        return "%02d:%02d".format(m, s)
    }
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
