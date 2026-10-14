package pg.mcxus.app.ui.theme

import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import pg.mcxus.app.R

/** McXus identity: deep Pacific blue, kina gold, Plus Jakarta Sans (see the approved design canvas). */
object Mx {
    val Navy = Color(0xFF0B2545)
    val Blue = Color(0xFF134074)
    val NavySoft = Color(0xFF13355E)
    val Gold = Color(0xFFE9A23B)
    val GoldDeep = Color(0xFFB9771A)
    val GoldSoft = Color(0xFFFBEBD0)
    val GoldInk = Color(0xFF6B4706)
    val Ink = Color(0xFF0E1B2B)
    val Body = Color(0xFF263445)
    val Muted = Color(0xFF556274)
    val OnNavyMuted = Color(0xFFC9D6E6)
    val Bg = Color(0xFFF4F6F9)
    val ChatBg = Color(0xFFE9EEF4)
    val Card = Color.White
    val Line = Color(0xFFE2E7EE)
    val LineSoft = Color(0xFFEEF1F5)
    val Field = Color(0xFFDCE3EC)
    val ChipLine = Color(0xFFD5DCE5)
    val Tint = Color(0xFFE8EEF6)
    val Slate = Color(0xFFDCE4EE)
    val Green = Color(0xFF1B7F5A)
    val GreenSoft = Color(0xFFD5EFE5)
    val GreenInk = Color(0xFF0F5A3F)
    val Red = Color(0xFFB3261E)
    val Grey = Color(0xFF8FA3BA)
}

@OptIn(ExperimentalTextApi::class)
private fun jakarta(weight: Int) = Font(
    R.font.plus_jakarta_sans,
    weight = FontWeight(weight),
    variationSettings = FontVariation.Settings(FontVariation.weight(weight)),
)

val Jakarta = FontFamily(jakarta(400), jakarta(500), jakarta(600), jakarta(700), jakarta(800))

// No colour here: text takes the colour of what it sits on (white on navy buttons, ink elsewhere).
private val base = TextStyle(fontFamily = Jakarta)

private val typography = Typography(
    headlineLarge = base.copy(fontSize = 28.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp),
    headlineMedium = base.copy(fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = (-0.5).sp),
    titleLarge = base.copy(fontSize = 19.sp, fontWeight = FontWeight.Bold),
    titleMedium = base.copy(fontSize = 16.sp, fontWeight = FontWeight.Bold),
    titleSmall = base.copy(fontSize = 14.sp, fontWeight = FontWeight.Bold),
    bodyLarge = base.copy(fontSize = 15.sp, lineHeight = 21.sp),
    bodyMedium = base.copy(fontSize = 14.sp, lineHeight = 20.sp),
    bodySmall = base.copy(fontSize = 12.sp),
    labelLarge = base.copy(fontSize = 15.sp, fontWeight = FontWeight.Bold),
    labelMedium = base.copy(fontSize = 13.sp, fontWeight = FontWeight.SemiBold),
    labelSmall = base.copy(fontSize = 11.sp, fontWeight = FontWeight.SemiBold),
)

private val colors = lightColorScheme(
    primary = Mx.Navy,
    onPrimary = Color.White,
    primaryContainer = Mx.GoldSoft,
    onPrimaryContainer = Mx.GoldInk,
    secondary = Mx.Blue,
    onSecondary = Color.White,
    tertiary = Mx.Gold,
    onTertiary = Mx.Navy,
    background = Mx.Bg,
    onBackground = Mx.Ink,
    surface = Color.White,
    onSurface = Mx.Ink,
    surfaceVariant = Mx.Tint,
    onSurfaceVariant = Mx.Muted,
    outline = Mx.ChipLine,
    error = Mx.Red,
)

@Composable
fun McXusTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, typography = typography) {
        CompositionLocalProvider(LocalContentColor provides Mx.Ink, content = content)
    }
}
