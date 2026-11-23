package com.example.streetview

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.annotation.StringRes
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.workDataOf
import com.example.streetview.ui.theme.FieldBackground
import com.example.streetview.ui.theme.StreetViewTheme
import com.example.streetview.ui.theme.enableFieldEdgeToEdge
import java.io.File

class RecordingsActivity : ComponentActivity() {

    // Compose-observable state holders
    private var reloadToken by mutableIntStateOf(0)
    private val archivingState = mutableStateMapOf<String, Boolean>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableFieldEdgeToEdge()

        setContent {
            StreetViewTheme {
                // Re-load sessions when background ZIP completes.
                val sessions = remember(reloadToken) { loadSessions() }

                FieldBackground {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .windowInsetsPadding(
                                WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)
                            ),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        RecordingsHeader(onBack = { onBackPressedDispatcher.onBackPressed() })

                        val bottomInset = WindowInsets.safeDrawing.asPaddingValues().calculateBottomPadding()
                        LazyColumn(
                            modifier = Modifier
                                .widthIn(max = 680.dp)
                                .fillMaxWidth()
                                .weight(1f),
                            contentPadding = PaddingValues(
                                start = 16.dp,
                                top = 12.dp,
                                end = 16.dp,
                                bottom = 16.dp + bottomInset
                            ),
                            verticalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            if (sessions.isEmpty()) {
                                item {
                                    OutlinedCard(
                                        modifier = Modifier.fillMaxWidth(),
                                        shape = RoundedCornerShape(16.dp),
                                        colors = CardDefaults.outlinedCardColors(
                                            containerColor = MaterialTheme.colorScheme.surfaceContainerLowest
                                        ),
                                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
                                    ) {
                                        Text(
                                            text = stringResource(R.string.recordings_empty),
                                            modifier = Modifier.padding(16.dp),
                                            style = MaterialTheme.typography.bodyMedium,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                            items(sessions, key = { it.baseName }) { s ->
                                val isArchiving = archivingState[s.baseName] == true
                                val hasZip = s.zip?.exists() == true
                                // The persistent marker prevents duplicate archives across app restarts.
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

    @Composable
    private fun RecordingsHeader(onBack: () -> Unit) {
        Row(
            modifier = Modifier
                .widthIn(max = 680.dp)
                .fillMaxWidth()
                .padding(start = 8.dp, top = 12.dp, end = 16.dp, bottom = 8.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            IconButton(onClick = onBack) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = stringResource(R.string.recordings_back),
                    tint = MaterialTheme.colorScheme.onSurface
                )
            }
            Column(
                modifier = Modifier.weight(1f).padding(top = 4.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                Text(
                    text = stringResource(R.string.recordings_title),
                    modifier = Modifier.semantics { heading() },
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = stringResource(R.string.recordings_subtitle),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
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

    @OptIn(ExperimentalLayoutApi::class)
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
        val colors = MaterialTheme.colorScheme
        val canShare = hasVideo || hasLog
        var menuExpanded by remember { mutableStateOf(false) }

        OutlinedCard(
            modifier = Modifier.fillMaxWidth().shadow(4.dp, RoundedCornerShape(20.dp), spotColor = colors.onSurface.copy(alpha = 0.40f)),
            shape = RoundedCornerShape(20.dp),
            colors = CardDefaults.outlinedCardColors(containerColor = colors.surface),
            border = BorderStroke(1.dp, colors.outlineVariant)
        ) {
            Column(modifier = Modifier.padding(start = 12.dp, top = 8.dp, end = 8.dp, bottom = 10.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    BoxWithConstraints(Modifier.weight(1f).padding(start = 4.dp)) {
                        val titleStyle = if (maxWidth < 228.dp) MaterialTheme.typography.titleMedium
                            else MaterialTheme.typography.titleLarge
                        Text(
                            text = title,
                            style = titleStyle,
                            fontWeight = FontWeight.Bold,
                            color = colors.onSurface
                        )
                    }

                    Box {
                        IconButton(onClick = { menuExpanded = true }) {
                            Icon(
                                imageVector = Icons.Filled.MoreVert,
                                contentDescription = stringResource(R.string.recordings_options, title),
                                tint = colors.onSurfaceVariant
                            )
                        }
                        DropdownMenu(expanded = menuExpanded, onDismissRequest = { menuExpanded = false }) {
                            DropdownMenuItem(
                                text = {
                                    Text(
                                        stringResource(
                                            when {
                                                isArchiving -> R.string.recordings_archiving
                                                hasZip -> R.string.recordings_archived_zip
                                                else -> R.string.recordings_archive_zip
                                            }
                                        )
                                    )
                                },
                                enabled = !isArchiving && !hasZip,
                                onClick = {
                                    menuExpanded = false
                                    onArchiveZip()
                                }
                            )

                            DropdownMenuItem(
                                text = { Text(stringResource(R.string.recordings_share_zip)) },
                                enabled = hasZip && !isArchiving,
                                onClick = {
                                    menuExpanded = false
                                    onShareZip()
                                }
                            )
                        }
                    }
                }

                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    SessionAction(
                        icon = Icons.Outlined.Map,
                        label = if (hasVideo) R.string.recordings_view_data else R.string.recordings_video_missing,
                        enabled = hasVideo,
                        onClick = onOpenVideo
                    )
                    SessionAction(
                        icon = Icons.Outlined.Description,
                        label = if (hasLog) R.string.recordings_open_log else R.string.recordings_log_missing,
                        enabled = hasLog,
                        onClick = onOpenLog
                    )
                    SessionAction(
                        icon = Icons.Outlined.Inventory2,
                        label = if (canShare) R.string.recordings_share else R.string.recordings_files_missing,
                        enabled = canShare,
                        onClick = onShareFiles
                    )
                }
            }
        }
    }

    @Composable
    private fun SessionAction(
        icon: ImageVector,
        @StringRes label: Int,
        enabled: Boolean,
        onClick: () -> Unit
    ) {
        TextButton(
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.heightIn(min = 48.dp),
            colors = ButtonDefaults.textButtonColors(
                contentColor = if (label == R.string.recordings_view_data) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.tertiary,
                disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.72f)
            ),
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 8.dp)
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                modifier = Modifier.size(20.dp),
                tint = if (enabled) MaterialTheme.colorScheme.primary else LocalContentColor.current
            )
            Spacer(Modifier.width(6.dp))
            Text(stringResource(label))
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
