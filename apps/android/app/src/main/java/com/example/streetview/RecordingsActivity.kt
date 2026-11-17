package com.example.streetview

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.example.streetview.ui.theme.StreetViewTheme
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MoreVert
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.io.File

class RecordingsActivity : ComponentActivity() {

    // Compose-observable state holders
    private var reloadToken by mutableIntStateOf(0)
    private val archivingState = mutableStateMapOf<String, Boolean>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            StreetViewTheme {
                val bg = Color(0xFFF6F7F9)
                val darkBlue = Color(0xFF0B2B3A)

                // Re-load sessions when background ZIP completes
                val token = reloadToken
                val sessions by remember(token) { mutableStateOf(loadSessions()) }

                Surface(modifier = Modifier.fillMaxSize(), color = bg) {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .statusBarsPadding()
                            .navigationBarsPadding()
                            .padding(16.dp)
                    ) {
                        Text(
                            text = "Recordings",
                            style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.Bold,
                            color = darkBlue,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        if (sessions.isEmpty()) {
                            Text("No recordings yet.", color = Color.Gray)
                        } else {
                            LazyColumn(
                                modifier = Modifier.fillMaxSize(),
                                verticalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                items(sessions) { s ->
                                    val isArchiving = archivingState[s.baseName] == true
                                    val hasZip = s.zip?.exists() == true
                                    // Persistent marker: if the app was killed/restarted while WorkManager is running,
                                    // we still show the UI as "Archiving…" and prevent double-trigger.
                                    val hasPending = s.zipPending?.exists() == true
                                    SessionCard(
                                        title = s.baseName,
                                        hasVideo = s.video != null,
                                        hasLog = s.log != null,
                                        isArchiving = isArchiving || hasPending,
                                        hasZip = hasZip,
                                        onOpenVideo = { s.video?.let { openFile(it, "video/mp4") } },
                                        onOpenLog = { s.log?.let { openFile(it, "text/plain") } },
                                        onShareFiles = { shareSessionFiles(s) },
                                        onArchiveZip = { archiveSessionZipAsync(s) },
                                        onShareZip = { shareZipFile(s) }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private data class Session(
        val baseName: String,
        val video: File?,
        val log: File?,
        val zip: File?,
        val zipPending: File?
    )

    private fun loadSessions(): List<Session> {
        val movies = File(getExternalFilesDir(Environment.DIRECTORY_MOVIES), "StreetView")
        val docs = File(getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS), "StreetView")
        val archives = File(docs, "Archives").apply { mkdirs() }

        val videos = movies.listFiles()?.filter { it.extension.lowercase() == "mp4" } ?: emptyList()
        val logs = docs.listFiles()?.filter { it.extension.lowercase() == "log" } ?: emptyList()

        val byBase = linkedMapOf<String, Session>()
        fun baseName(f: File): String = f.nameWithoutExtension

        fun zipFor(base: String) = File(archives, "$base.zip")
        fun pendingFor(base: String) = File(archives, "$base.zip.pending")

        videos.forEach { v ->
            val b = baseName(v)
            val existing = byBase[b]
            val zip = zipFor(b)
            val pending = pendingFor(b)
            byBase[b] = Session(b, v, existing?.log, zip, pending)
        }

        logs.forEach { l ->
            val b = baseName(l)
            val existing = byBase[b]
            val zip = zipFor(b)
            val pending = pendingFor(b)
            byBase[b] = Session(b, existing?.video, l, zip, pending)
        }

        return byBase.values.sortedByDescending { it.baseName }
    }

    @Composable
    private fun SessionCard(
        title: String,
        hasVideo: Boolean,
        hasLog: Boolean,
        isArchiving: Boolean,
        hasZip: Boolean,
        onOpenVideo: () -> Unit,
        onOpenLog: () -> Unit,
        onShareFiles: () -> Unit,
        onArchiveZip: () -> Unit,
        onShareZip: () -> Unit
    ) {
        val darkBlue = Color(0xFF0B2B3A)
        val orange = Color(0xFFFF7A00)

        val canShare = hasVideo || hasLog

        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                var menuExpanded by remember { mutableStateOf(false) }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(title, fontWeight = FontWeight.Bold, color = darkBlue)

                    Box {
                        IconButton(onClick = { menuExpanded = true }) {
                            Icon(imageVector = Icons.Filled.MoreVert, contentDescription = "Options")
                        }
                        DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                            DropdownMenuItem(
                                text = {
                                    Text(
                                        when {
                                            isArchiving -> "Archiving…"
                                            hasZip -> "Archived (ZIP)"
                                            else -> "Archive (ZIP)"
                                        }
                                    )
                                },
                                enabled = !isArchiving && !hasZip,
                                onClick = {
                                    menuExpanded = false
                                    onArchiveZip()
                                }
                            )

                            DropdownMenuItem(
                                text = { Text("Share ZIP") },
                                enabled = hasZip && !isArchiving,
                                onClick = {
                                    menuExpanded = false
                                    onShareZip()
                                }
                            )
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = if (hasVideo) "🗺️ View data" else "🗺️ Missing",
                        color = if (hasVideo) orange else Color.Gray,
                        modifier = Modifier
                            .clickable(enabled = hasVideo) { onOpenVideo() }
                            .padding(vertical = 6.dp, horizontal = 8.dp)
                    )

                    Text(
                        text = if (hasLog) "🧾 Open log" else "🧾 Missing",
                        color = if (hasLog) orange else Color.Gray,
                        modifier = Modifier
                            .clickable(enabled = hasLog) { onOpenLog() }
                            .padding(vertical = 6.dp, horizontal = 8.dp)
                    )

                    Text(
                        text = if (canShare) "📦 Share" else "📦 Missing",
                        color = if (canShare) orange else Color.Gray,
                        modifier = Modifier
                            .clickable(enabled = canShare) { onShareFiles() }
                            .padding(vertical = 6.dp, horizontal = 8.dp)
                    )
                }
            }
        }
    }

    private fun openFile(file: File, mime: String) {
        val uri: Uri = FileProvider.getUriForFile(
            this,
            "${packageName}.fileprovider",
            file
        )

        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, mime)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(intent, "Open"))
    }

    /**
     * Fast share: shares mp4 + log without zipping (no UI freeze).
     */
    private fun shareSessionFiles(session: Session) {
        val uris = arrayListOf<Uri>()

        session.video?.takeIf { it.exists() }?.let { uris.add(getContentUri(it)) }
        session.log?.takeIf { it.exists() }?.let { uris.add(getContentUri(it)) }

        if (uris.isEmpty()) return

        val intent = Intent(Intent.ACTION_SEND_MULTIPLE).apply {
            type = "*/*"
            putParcelableArrayListExtra(Intent.EXTRA_STREAM, uris)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }

        startActivity(Intent.createChooser(intent, "Share session"))
    }

    /**
     * Background archive: creates ZIP in Documents/StreetView/Archives without blocking UI.
     */
    private fun archiveSessionZipAsync(session: Session) {
        val docs = File(getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS), "StreetView")
        val archives = File(docs, "Archives").apply { mkdirs() }
        val zipFile = File(archives, "${session.baseName}.zip")
        val pending = File(archives, "${session.baseName}.zip.pending")

        // If already archiving, ignore double taps.
        if (archivingState[session.baseName] == true) return
        // If the ZIP already exists, or we already started archiving earlier, do nothing.
        if (zipFile.exists() || pending.exists()) {
            reloadToken++
            return
        }
        archivingState[session.baseName] = true

        // Persistent marker so the UI stays friendly even if the app is killed while archiving.
        try { pending.writeText("pending") } catch (_: Exception) {}

        val req = OneTimeWorkRequestBuilder<ZipSessionWorker>()
            .addTag("zip_${session.baseName}")
            .setInputData(
                workDataOf(
                    ZipSessionWorker.KEY_BASE_NAME to session.baseName,
                    ZipSessionWorker.KEY_ZIP_PATH to zipFile.absolutePath,
                    ZipSessionWorker.KEY_VIDEO_PATH to session.video?.absolutePath,
                    ZipSessionWorker.KEY_LOG_PATH to session.log?.absolutePath,
                )
            )
            .build()

        val wm = WorkManager.getInstance(this)
        try {
            wm.enqueue(req)
        } catch (t: Throwable) {
            // Keep the app alive: clean up and reset UI state.
            archivingState[session.baseName] = false
            try { pending.delete() } catch (_: Exception) {}
            reloadToken++
            return
        }

        // Observe completion; then refresh UI.
        wm.getWorkInfoByIdLiveData(req.id).observe(this) { info ->
            if (info == null) return@observe
            if (info.state == WorkInfo.State.SUCCEEDED || info.state == WorkInfo.State.FAILED || info.state == WorkInfo.State.CANCELLED) {
                archivingState[session.baseName] = false
                reloadToken++
            }
        }
    }

    private fun shareZipFile(session: Session) {
        val zip = session.zip ?: return
        if (!zip.exists()) return
        val zipUri = getContentUri(zip)

        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = "application/zip"
            putExtra(Intent.EXTRA_STREAM, zipUri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }

        startActivity(Intent.createChooser(shareIntent, "Share ZIP"))
    }

    private fun getContentUri(file: File): Uri {
        return FileProvider.getUriForFile(
            this,
            "${packageName}.fileprovider",
            file
        )
    }
}
