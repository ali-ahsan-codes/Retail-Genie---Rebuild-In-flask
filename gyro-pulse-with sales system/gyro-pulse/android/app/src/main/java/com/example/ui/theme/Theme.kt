package com.example.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun Modifier.grainBackground(): Modifier {
    val dotColor = Color(0xFFFF8C42).copy(alpha = 0.12f)
    return this.drawBehind {
        val dotRadius = 1.5.dp.toPx()
        val gap = 24.dp.toPx()
        val columns = (size.width / gap).toInt() + 1
        val rows = (size.height / gap).toInt() + 1
        for (c in 0 until columns) {
            for (r in 0 until rows) {
                drawCircle(
                    color = dotColor,
                    radius = dotRadius,
                    center = Offset(c * gap, r * gap)
                )
            }
        }
    }
}

// Map to system SansSerif for compile-time safety and visual polish
private val PlusJakartaSans = FontFamily.SansSerif

private val AppTypography = Typography(
    displayLarge = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Bold,
        fontSize = 40.sp,
        lineHeight = 48.sp,
        letterSpacing = (-0.02).sp
    ),
    headlineLarge = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Bold,
        fontSize = 32.sp,
        lineHeight = 40.sp,
        letterSpacing = (-0.01).sp
    ),
    headlineMedium = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 24.sp,
        lineHeight = 32.sp
    ),
    headlineSmall = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 28.sp
    ),
    bodyLarge = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Normal,
        fontSize = 18.sp,
        lineHeight = 28.sp
    ),
    bodyMedium = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp
    ),
    labelLarge = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        letterSpacing = 0.01.sp
    ),
    labelMedium = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp
    ),
    titleLarge = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 22.sp,
        lineHeight = 28.sp
    ),
    titleMedium = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Medium,
        fontSize = 16.sp,
        lineHeight = 24.sp
    ),
    bodySmall = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp
    ),
    labelSmall = TextStyle(
        fontFamily = PlusJakartaSans,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 16.sp
    )
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(32.dp)
)

private val DarkColorScheme =
    darkColorScheme(
        primary = MidnightPrimary,
        onPrimary = MidnightOnPrimary,
        primaryContainer = MidnightPrimaryContainer,
        onPrimaryContainer = MidnightOnPrimaryContainer,
        secondary = MidnightSecondary,
        onSecondary = MidnightOnSecondary,
        secondaryContainer = MidnightSecondaryContainer,
        onSecondaryContainer = MidnightOnSecondaryContainer,
        tertiary = MidnightTertiary,
        onTertiary = MidnightOnTertiary,
        tertiaryContainer = MidnightTertiaryContainer,
        onTertiaryContainer = MidnightOnTertiaryContainer,
        background = MidnightBackground,
        onBackground = MidnightOnBackground,
        surface = MidnightSurface,
        onSurface = MidnightOnSurface,
        surfaceVariant = MidnightSurfaceVariant,
        onSurfaceVariant = MidnightOnSurfaceVariant,
        outline = MidnightOutline,
        outlineVariant = MidnightOutlineVariant,
        error = MidnightError,
        onError = MidnightOnError,
        errorContainer = MidnightErrorContainer,
        onErrorContainer = MidnightOnErrorContainer
    )

private val LightColorScheme =
    lightColorScheme(
        primary = AurenePrimary,
        onPrimary = AureneOnPrimary,
        primaryContainer = AurenePrimaryContainer,
        onPrimaryContainer = AureneOnPrimaryContainer,
        secondary = AureneSecondary,
        onSecondary = AureneOnSecondary,
        secondaryContainer = AureneSecondaryContainer,
        onSecondaryContainer = AureneOnSecondaryContainer,
        tertiary = AureneTertiary,
        onTertiary = AureneOnTertiary,
        tertiaryContainer = AureneTertiaryContainer,
        onTertiaryContainer = AureneOnTertiaryContainer,
        background = AureneBackground,
        onBackground = AureneOnBackground,
        surface = AureneSurface,
        onSurface = AureneOnSurface,
        surfaceVariant = AureneSurfaceVariant,
        onSurfaceVariant = AureneOnSurfaceVariant,
        outline = AureneOutline,
        outlineVariant = AureneOutlineVariant,
        error = AureneError,
        onError = AureneOnError,
        errorContainer = AureneErrorContainer,
        onErrorContainer = AureneOnErrorContainer
    )

@Composable
fun MyApplicationTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit
) {
    val colorScheme =
        when {
            dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
                val context = LocalContext.current
                if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
            }
            darkTheme -> DarkColorScheme
            else -> LightColorScheme
        }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = AppTypography,
        shapes = AppShapes,
        content = content
    )
}
