package com.example.streetview.ui.theme

import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.colorResource
import androidx.compose.ui.unit.dp
import com.example.streetview.R

fun ComponentActivity.enableFieldEdgeToEdge() {
    val transparent = android.graphics.Color.TRANSPARENT
    enableEdgeToEdge(
        statusBarStyle = SystemBarStyle.light(transparent, transparent),
        navigationBarStyle = SystemBarStyle.light(transparent, 0x660B2B3C)
    )
}

@Composable
fun StreetViewTheme(content: @Composable () -> Unit) {
    val ink = colorResource(R.color.field_ink)
    val white = colorResource(R.color.field_surface)
    val background = colorResource(R.color.field_background)
    val blue = colorResource(R.color.field_blue)
    val secondary = colorResource(R.color.field_secondary)
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = blue, onPrimary = white,
            secondary = secondary, onSecondary = white,
            secondaryContainer = colorResource(R.color.field_blue_tint), onSecondaryContainer = ink,
            tertiary = colorResource(R.color.field_orange_dark), onTertiary = white,
            background = background, onBackground = ink,
            surface = white, onSurface = ink, onSurfaceVariant = secondary,
            surfaceContainerLowest = white,
            surfaceContainerLow = background,
            surfaceContainer = background,
            surfaceContainerHigh = colorResource(R.color.field_blue_tint),
            outline = secondary,
            outlineVariant = colorResource(R.color.field_border)
        ),
        typography = Typography,
        content = content
    )
}

@Composable
fun FieldBackground(content: @Composable BoxScope.() -> Unit) {
    val contour = colorResource(R.color.field_contour)
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Canvas(Modifier.matchParentSize()) {
            val w = size.width
            val h = minOf(size.height, 760.dp.toPx())
            repeat(7) { index ->
                val n = index.toFloat()
                val dy = h * n * 0.020f
                val path = Path().apply {
                    moveTo(-0.09f * w, h * 0.38f + dy)
                    cubicTo(w * (0.22f + n * 0.018f), h * 0.36f + dy, w * 0.19f, h * 0.18f + dy, w * 0.44f, h * 0.19f + dy)
                    cubicTo(w * 0.64f, h * 0.20f + dy, w * (0.62f + n * 0.012f), h * 0.075f + dy, w * 0.80f, h * 0.11f + dy)
                    cubicTo(w * 0.88f, h * 0.13f + dy, w * 0.94f, h * 0.17f + dy, w * 1.08f, h * 0.11f + dy)
                }
                drawPath(path, contour.copy(alpha = 0.68f - index * 0.05f), style = Stroke(0.9.dp.toPx()))
            }
        }
        content()
    }
}
