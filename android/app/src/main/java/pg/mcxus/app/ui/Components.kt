package pg.mcxus.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images

@Composable
fun StarLogo(size: Dp = 30.dp) {
    Box(
        Modifier.size(size).clip(RoundedCornerShape(size * 0.26f)).background(Mx.Navy),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Ic.Star, contentDescription = "McXus", tint = Mx.Gold, modifier = Modifier.size(size * 0.62f))
    }
}

fun initials(name: String): String =
    name.split(" ", ".", "-").filter { it.isNotBlank() }.take(2).joinToString("") { it.first().uppercase() }.ifEmpty { "?" }

private val avatarColors = listOf(
    Mx.Blue to Color.White, Mx.GoldSoft to Mx.GoldInk, Mx.GreenSoft to Mx.GreenInk, Mx.Slate to Mx.Blue,
)

@Composable
fun Avatar(name: String, size: Dp = 50.dp, ring: Color? = null, key: String = name) {
    val (bg, fg) = avatarColors[(key.hashCode() and 0x7fffffff) % avatarColors.size]
    val inner = Modifier.size(size).clip(CircleShape).background(bg)
    Box(
        if (ring != null) inner.border(2.dp, ring, CircleShape) else inner,
        contentAlignment = Alignment.Center,
    ) {
        Text(initials(name), color = fg, fontWeight = FontWeight.Bold, fontSize = (size.value * 0.32f).sp)
    }
}

/** Round avatar for a chat: a person's initials, or the group icon on navy. */
@Composable
fun ChatAvatar(c: pg.mcxus.app.chat.Conversation, size: Dp = 50.dp, ring: Color? = null) {
    if (!c.isGroup) {
        Avatar(c.name, size, ring, key = c.avatarKey)
        return
    }
    val inner = Modifier.size(size).clip(CircleShape).background(Mx.Navy)
    Box(if (ring != null) inner.border(2.dp, ring, CircleShape) else inner, contentAlignment = Alignment.Center) {
        Icon(Ic.Group, contentDescription = null, tint = Mx.Gold, modifier = Modifier.size(size * 0.5f))
    }
}

@Composable
fun Tag(text: String, bg: Color = Mx.GoldSoft, fg: Color = Mx.GoldInk) {
    Text(
        text,
        modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(bg).padding(horizontal = 6.dp, vertical = 2.dp),
        color = fg, fontSize = 10.sp, fontWeight = FontWeight.Bold, maxLines = 1,
    )
}

@Composable
fun SellerBadge(badge: String) {
    if (badge.isEmpty()) return
    if (badge == "caution") Tag(Format.badge(badge), Color(0xFFFDE2E1), Mx.Red) else Tag(Format.badge(badge))
}

@Composable
fun Pill(label: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(17.dp)
    Box(
        modifier.height(34.dp).clip(shape)
            .background(if (selected) Mx.Blue else Color.White)
            .then(if (selected) Modifier else Modifier.border(1.dp, Mx.ChipLine, shape))
            .clickable(onClick = onClick).padding(horizontal = 14.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = if (selected) Color.White else Mx.Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun RoundIcon(icon: ImageVector, label: String, onClick: () -> Unit, bg: Color = Color.White, tint: Color = Mx.Blue) {
    IconButton(onClick = onClick, modifier = Modifier.size(44.dp).clip(CircleShape).background(bg)) {
        Icon(icon, contentDescription = label, tint = tint, modifier = Modifier.size(22.dp))
    }
}

@Composable
fun BigButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    busy: Boolean = false,
    color: Color = Mx.Navy,
    textColor: Color = Color.White,
    icon: (@Composable () -> Unit)? = null,
) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        modifier = modifier.fillMaxWidth().height(52.dp),
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = color, contentColor = textColor),
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(20.dp), color = textColor, strokeWidth = 2.dp)
        } else {
            icon?.invoke()
            if (icon != null) Spacer(Modifier.width(8.dp))
            Text(text, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
        }
    }
}

@Composable
fun LineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = Mx.Blue, enabled: Boolean = true) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(48.dp),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(2.dp, if (enabled) color.copy(alpha = 0.6f) else Mx.ChipLine),
        contentPadding = PaddingValues(horizontal = 16.dp),
    ) {
        Text(text, color = color, fontWeight = FontWeight.Bold, fontSize = 14.sp, textAlign = TextAlign.Center)
    }
}

@Composable
fun Field(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    keyboard: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    minLines: Int = 1,
    tag: String = label,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = singleLine,
        minLines = minLines,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Mx.Blue, unfocusedBorderColor = Mx.Field,
            focusedContainerColor = Color.White, unfocusedContainerColor = Color.White,
        ),
        modifier = modifier.fillMaxWidth().testTag(tag),
    )
}

/** Screen header like the design: big bold title on the light background, actions on the right. */
@Composable
fun Header(title: String, onBack: (() -> Unit)? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().statusBarsPadding().padding(start = if (onBack != null) 4.dp else 16.dp, end = 12.dp, top = 12.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (onBack != null) {
            IconButton(onClick = onBack) { Icon(Ic.Back, contentDescription = "Back", tint = Mx.Ink) }
        }
        Text(
            title,
            style = if (onBack != null) androidx.compose.material3.MaterialTheme.typography.titleLarge
            else androidx.compose.material3.MaterialTheme.typography.headlineMedium,
            modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
        actions()
    }
}

@Composable
fun Card(modifier: Modifier = Modifier, padding: Dp = 14.dp, content: @Composable () -> Unit) {
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Color.White).padding(padding)) { content() }
}

@Composable
fun Note(text: String, modifier: Modifier = Modifier, icon: ImageVector = Ic.Shield, dark: Boolean = false) {
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (dark) Mx.Navy else Mx.GoldSoft)
            .padding(horizontal = 12.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(icon, null, tint = if (dark) Mx.Gold else Mx.GoldInk, modifier = Modifier.size(18.dp))
        Text(text, color = if (dark) Color.White else Color(0xFF4A3105), fontSize = 12.sp, lineHeight = 17.sp)
    }
}

@Composable
fun Loading(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(color = Mx.Blue)
    }
}

@Composable
fun Empty(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier.fillMaxWidth().padding(32.dp), color = Mx.Muted, textAlign = TextAlign.Center, fontSize = 14.sp)
}

/** A listing photo from the server (path like /media/…), with a soft placeholder while it loads. */
@Composable
fun RemoteImage(path: String?, modifier: Modifier = Modifier, label: String = "") {
    val app = LocalApp.current
    val url = if (path.isNullOrEmpty()) null else if (path.startsWith("http")) path else app.session.server.trimEnd('/') + path
    var bitmap by remember(url) { mutableStateOf(url?.let { Images.cached(it) }) }
    LaunchedEffect(url) { if (url != null && bitmap == null) bitmap = Images.load(url) }
    Box(modifier.background(Mx.Slate), contentAlignment = Alignment.Center) {
        val b = bitmap
        if (b != null) {
            Image(b.asImageBitmap(), contentDescription = label, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        } else {
            Icon(Ic.Market, contentDescription = null, tint = Mx.Grey, modifier = Modifier.size(28.dp))
        }
    }
}

@Composable
fun StarsAmount(amount: String, big: Boolean = false) {
    Row(verticalAlignment = Alignment.Bottom) {
        Text(Format.kina(amount), color = Mx.Blue, fontWeight = FontWeight.ExtraBold, fontSize = if (big) 28.sp else 15.sp)
        Text(" · ${amount.removeSuffix(".00")} Stars", color = Mx.Muted, fontWeight = FontWeight.SemiBold, fontSize = if (big) 14.sp else 12.sp,
            modifier = Modifier.padding(bottom = if (big) 4.dp else 1.dp))
    }
}
