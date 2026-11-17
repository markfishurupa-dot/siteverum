package com.example.streetview

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.camera2.*
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.media.MediaRecorder
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.max

class RecordingService : Service() {

    companion object {
        const val ACTION_START = "com.example.streetview.action.START"
        const val ACTION_STOP = "com.example.streetview.action.STOP"
        const val ACTION_QUERY_STATUS = "com.example.streetview.action.QUERY_STATUS"

        const val ACTION_STATUS_BROADCAST = "com.example.streetview.action.STATUS"
        const val EXTRA_IS_RECORDING = "isRecording"
        const val EXTRA_SPEED = "speed"
        const val EXTRA_ACCURACY = "accuracy"
        const val EXTRA_POINTS = "points"
        const val EXTRA_ELAPSED_MS = "elapsedMs"
        const val EXTRA_FILE_NAME = "fileName"

        private const val CHANNEL_ID = "streetview_recording"
        private const val NOTIF_ID = 1001
    }

    private var isRecording = false

    private var cameraDevice: CameraDevice? = null
    private var captureSession: CameraCaptureSession? = null
    private var mediaRecorder: MediaRecorder? = null

    private var videoFile: File? = null
    private var logFile: File? = null
    private var logWriter: FileWriter? = null

    private var locationManager: LocationManager? = null

    // wall-clock ms at actual MediaRecorder.start()
    private var startTimeMs: Long = 0L
    // SystemClock.elapsedRealtime() at MediaRecorder.start() (monotonic)
    private var startElapsedMs: Long = 0L

    private var pointsCount: Int = 0
    private var lastSpeedMps: Float = 0f
    private var lastAccuracyM: Float = 0f

    private val handler = Handler(Looper.getMainLooper())
    private val ticker = object : Runnable {
        override fun run() {
            if (isRecording) {
                broadcastStatus()
                updateNotification(buildNotificationText())
                handler.postDelayed(this, 1000)
            }
        }
    }

    private val locationListener = object : LocationListener {
        override fun onLocationChanged(location: Location) {
            pointsCount += 1
            lastSpeedMps = location.speed
            lastAccuracyM = location.accuracy
            writeLog(location)

            broadcastStatus()
            updateNotification(buildNotificationText())
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRecording()
            ACTION_STOP -> stopRecording()
            ACTION_QUERY_STATUS -> broadcastStatus()
        }
        return START_STICKY
    }

    private fun startRecording() {
        if (isRecording) return
        if (!hasAllPermissions()) {
            stopSelf()
            return
        }

        startForeground(NOTIF_ID, buildNotification("Starting…"))

        try {
            prepareOutputFiles()
            openLogWriter()

            // reset actual-video-start stamps
            startTimeMs = 0L
            startElapsedMs = 0L

            pointsCount = 0
            lastSpeedMps = 0f
            lastAccuracyM = 0f

            startLocationUpdates()
            setupMediaRecorderVideoOnly()
            openCameraAndStartSession()

            isRecording = true
            handler.removeCallbacks(ticker)
            handler.post(ticker)

            broadcastStatus()
            updateNotification(buildNotificationText())
        } catch (e: Exception) {
            e.printStackTrace()
            updateNotification("Recording failed ❌")
            cleanupEverything()
            stopSelf()
        }
    }

    private fun stopRecording() {
        if (!isRecording) {
            stopSelf()
            return
        }

        handler.removeCallbacks(ticker)

        try {
            captureSession?.stopRepeating()
            captureSession?.abortCaptures()
        } catch (_: Exception) {}

        try {
            mediaRecorder?.apply {
                try { stop() } catch (_: Exception) {}
                reset()
                release()
            }
        } catch (_: Exception) {}
        mediaRecorder = null

        try { captureSession?.close() } catch (_: Exception) {}
        captureSession = null

        try { cameraDevice?.close() } catch (_: Exception) {}
        cameraDevice = null

        stopLocationUpdates()
        closeLogWriter()

        isRecording = false
        broadcastStatus()
        updateNotification("Saved ✅\n${videoFile?.name ?: ""}")

        stopForeground(STOP_FOREGROUND_DETACH)
        stopSelf()
    }

    private fun prepareOutputFiles() {
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())

        val moviesDir = getExternalFilesDir(Environment.DIRECTORY_MOVIES)
        val docsDir = getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS)

        val videoDir = File(moviesDir, "StreetView").apply { mkdirs() }
        val logsDir = File(docsDir, "StreetView").apply { mkdirs() }

        videoFile = File(videoDir, "SV_$ts.mp4")
        logFile = File(logsDir, "SV_$ts.log")

        videoFile!!.createNewFile()
        logFile!!.createNewFile()
    }

    private fun openLogWriter() {
        logWriter = FileWriter(logFile!!, true)
        logWriter?.write(
            "timestamp_utc,video_elapsed_ms,recording_start_utc_ms,lat,lon,accuracy_m,speed_mps,bearing,alt_m\n"
        )
        logWriter?.flush()
    }

    private fun closeLogWriter() {
        try { logWriter?.flush() } catch (_: Exception) {}
        try { logWriter?.close() } catch (_: Exception) {}
        logWriter = null
    }

    private fun writeLog(loc: Location) {
        val w = logWriter ?: return

        val nowUtcMs = System.currentTimeMillis()
        val videoElapsedMs = if (startElapsedMs > 0L) {
            max(0L, SystemClock.elapsedRealtime() - startElapsedMs)
        } else {
            -1L // video not started yet
        }
        val recordingStartUtcMs = if (startTimeMs > 0L) startTimeMs else -1L

        val line = buildString {
            append(nowUtcMs).append(",")
            append(videoElapsedMs).append(",")
            append(recordingStartUtcMs).append(",")
            append(loc.latitude).append(",")
            append(loc.longitude).append(",")
            append(loc.accuracy).append(",")
            append(loc.speed).append(",")
            append(loc.bearing).append(",")
            append(loc.altitude).append("\n")
        }

        try {
            w.write(line)
            w.flush()
        } catch (_: Exception) {}
    }

    private fun startLocationUpdates() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) return

        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val lm = locationManager ?: return

        try {
            lm.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                1000L,
                0f,
                locationListener,
                Looper.getMainLooper()
            )
        } catch (_: SecurityException) {}

        try {
            lm.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER,
                1000L,
                0f,
                locationListener,
                Looper.getMainLooper()
            )
        } catch (_: SecurityException) {}
    }

    private fun stopLocationUpdates() {
        try { locationManager?.removeUpdates(locationListener) } catch (_: Exception) {}
        locationManager = null
    }

    // ✅ VIDEO ONLY MediaRecorder
    private fun setupMediaRecorderVideoOnly() {
        val file = videoFile ?: throw IllegalStateException("videoFile is null")

        val prefs = getSharedPreferences(QualityPrefs.PREFS, Context.MODE_PRIVATE)
        val mode = QualityPrefs.getQuality(prefs)

        val (w, h, fps, bitrate) = if (mode == QualityPrefs.QUALITY_OPTIMIZED) {
            Quad(1280, 720, 20, 2_000_000)
        } else {
            Quad(1920, 1080, 24, 4_000_000)
        }

        mediaRecorder = MediaRecorder().apply {
            setVideoSource(MediaRecorder.VideoSource.SURFACE)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setOutputFile(file.absolutePath)

            setVideoEncodingBitRate(bitrate)
            setVideoFrameRate(fps)
            setVideoSize(w, h)
            setVideoEncoder(MediaRecorder.VideoEncoder.H264)

            prepare()
        }
    }

    private data class Quad(val w: Int, val h: Int, val fps: Int, val bitrate: Int)

    private fun openCameraAndStartSession() {
        val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val cameraId = cameraManager.cameraIdList.firstOrNull { id ->
            val chars = cameraManager.getCameraCharacteristics(id)
            chars.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: cameraManager.cameraIdList.first()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            throw SecurityException("CAMERA permission missing")
        }

        cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
            override fun onOpened(device: CameraDevice) {
                cameraDevice = device
                createCaptureSession(device)
            }

            override fun onDisconnected(device: CameraDevice) {
                device.close()
                cameraDevice = null
                stopRecording()
            }

            override fun onError(device: CameraDevice, error: Int) {
                device.close()
                cameraDevice = null
                stopRecording()
            }
        }, null)
    }

    private fun createCaptureSession(device: CameraDevice) {
        val recorder = mediaRecorder ?: throw IllegalStateException("mediaRecorder null")
        val recorderSurface = recorder.surface

        val request = device.createCaptureRequest(CameraDevice.TEMPLATE_RECORD).apply {
            addTarget(recorderSurface)
            set(CaptureRequest.CONTROL_MODE, CameraMetadata.CONTROL_MODE_AUTO)
        }.build()

        device.createCaptureSession(
            listOf(recorderSurface),
            object : CameraCaptureSession.StateCallback() {
                override fun onConfigured(session: CameraCaptureSession) {
                    captureSession = session
                    try {
                        session.setRepeatingRequest(request, null, null)

                        // ✅ stamp the *actual* moment video starts (for log/video sync)
                        startTimeMs = System.currentTimeMillis()
                        startElapsedMs = SystemClock.elapsedRealtime()

                        recorder.start()
                        broadcastStatus()
                        updateNotification(buildNotificationText())
                    } catch (e: Exception) {
                        e.printStackTrace()
                        stopRecording()
                    }
                }

                override fun onConfigureFailed(session: CameraCaptureSession) {
                    stopRecording()
                }
            },
            null
        )
    }

    private fun cleanupEverything() {
        handler.removeCallbacks(ticker)

        try { captureSession?.close() } catch (_: Exception) {}
        captureSession = null

        try { cameraDevice?.close() } catch (_: Exception) {}
        cameraDevice = null

        try {
            mediaRecorder?.apply {
                try { stop() } catch (_: Exception) {}
                reset()
                release()
            }
        } catch (_: Exception) {}
        mediaRecorder = null

        stopLocationUpdates()
        closeLogWriter()
        isRecording = false
    }

    private fun hasAllPermissions(): Boolean {
        val mustHave = listOf(
            Manifest.permission.CAMERA,
            Manifest.permission.ACCESS_FINE_LOCATION
        )
        return mustHave.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun broadcastStatus() {
        val elapsed = if (isRecording && startTimeMs > 0L) System.currentTimeMillis() - startTimeMs else 0L
        val i = Intent(ACTION_STATUS_BROADCAST).apply {
            setPackage(packageName)
            putExtra(EXTRA_IS_RECORDING, isRecording)
            putExtra(EXTRA_SPEED, lastSpeedMps)
            putExtra(EXTRA_ACCURACY, lastAccuracyM)
            putExtra(EXTRA_POINTS, pointsCount)
            putExtra(EXTRA_ELAPSED_MS, max(0L, elapsed))
            putExtra(EXTRA_FILE_NAME, videoFile?.name ?: "")
        }
        sendBroadcast(i)
    }

    private fun buildNotificationText(): String {
        val elapsed = if (isRecording && startTimeMs > 0L) System.currentTimeMillis() - startTimeMs else 0L
        val mmss = formatElapsed(elapsed)
        val kmh = lastSpeedMps * 3.6f
        return if (isRecording) {
            "Recording ✅  ${videoFile?.name ?: ""}\n" +
                    "Speed: ${"%.1f".format(kmh)} km/h | Acc: ${"%.1f".format(lastAccuracyM)} m | Points: $pointsCount | Time: $mmss"
        } else "Idle"
    }

    private fun formatElapsed(ms: Long): String {
        val totalSec = max(0L, ms) / 1000L
        val m = totalSec / 60L
        val s = totalSec % 60L
        return "%02d:%02d".format(m, s)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "StreetView Recording", NotificationManager.IMPORTANCE_LOW)
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(ch)
        }
    }

    private fun buildNotification(text: String): Notification {
        val stopIntent = Intent(this, RecordingService::class.java).apply { action = ACTION_STOP }
        val stopPending = PendingIntent.getService(
            this, 2, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        val openIntent = Intent(this, MainActivity::class.java)
        val openPending = PendingIntent.getActivity(
            this, 1, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 23) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("StreetView")
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(openPending)
            .addAction(0, "Stop", stopPending)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIF_ID, buildNotification(text))
    }
}