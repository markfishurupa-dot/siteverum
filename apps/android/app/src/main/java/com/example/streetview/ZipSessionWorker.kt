package com.example.streetview

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * Creates a ZIP archive for a recording session in the background.
 *
 * Input data keys:
 *  - baseName
 *  - zipPath
 *  - videoPath (optional)
 *  - logPath (optional)
 */
class ZipSessionWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    companion object {
        const val KEY_BASE_NAME = "baseName"
        const val KEY_ZIP_PATH = "zipPath"
        const val KEY_VIDEO_PATH = "videoPath"
        const val KEY_LOG_PATH = "logPath"

        private const val CHANNEL_ID = "streetview_zip"
        private const val NOTIF_ID = 2001
    }

    override suspend fun doWork(): Result {
        val baseName = inputData.getString(KEY_BASE_NAME) ?: return Result.failure()
        val zipPath = inputData.getString(KEY_ZIP_PATH) ?: return Result.failure()
        val videoPath = inputData.getString(KEY_VIDEO_PATH)
        val logPath = inputData.getString(KEY_LOG_PATH)

        setForeground(createForegroundInfo(baseName))

        val zipFile = File(zipPath)
        zipFile.parentFile?.mkdirs()

        // Marker created by UI to indicate "archiving started" across app restarts.
        val pendingMarker = File(zipPath + ".pending")

        // Write to temp file first, then rename. Prevents half-written ZIPs.
        val tmp = File(zipFile.parentFile, zipFile.name + ".tmp")
        if (tmp.exists()) tmp.delete()
        if (zipFile.exists()) zipFile.delete()

        return try {
            ZipOutputStream(FileOutputStream(tmp)).use { zos ->
                videoPath?.let { p ->
                    val f = File(p)
                    if (f.exists()) addToZip(zos, f)
                }
                logPath?.let { p ->
                    val f = File(p)
                    if (f.exists()) addToZip(zos, f)
                }
            }

            // Atomic-ish replace
            if (!tmp.renameTo(zipFile)) {
                // Fallback copy
                FileInputStream(tmp).use { input ->
                    FileOutputStream(zipFile).use { out -> input.copyTo(out) }
                }
                tmp.delete()
            }

            Result.success()
        } catch (t: Throwable) {
            try { tmp.delete() } catch (_: Exception) {}
            Result.failure()
        } finally {
            try { pendingMarker.delete() } catch (_: Exception) {}
        }
    }

    private fun addToZip(zos: ZipOutputStream, file: File) {
        FileInputStream(file).use { fis ->
            zos.putNextEntry(ZipEntry(file.name))
            fis.copyTo(zos)
            zos.closeEntry()
        }
    }

    private fun createForegroundInfo(baseName: String): ForegroundInfo {
        createChannelIfNeeded()
        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("StreetView")
            .setContentText("Archiving $baseName…")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(0, 0, true) // indeterminate
            .build()

        // Android 14/15 (and targetSdk 34+) requires an explicit foreground service type.
        // Without this, WorkManager's SystemForegroundService may crash with:
        // InvalidForegroundServiceTypeException: Starting FGS with type none ... prohibited
        val fgsType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        } else {
            0
        }
        return ForegroundInfo(NOTIF_ID, notification, fgsType)
    }

    private fun createChannelIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                "StreetView Archiving",
                NotificationManager.IMPORTANCE_LOW
            )
            nm.createNotificationChannel(ch)
        }
    }
}
