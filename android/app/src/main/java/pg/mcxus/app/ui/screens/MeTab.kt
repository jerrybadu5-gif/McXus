package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import pg.mcxus.app.BuildConfig
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.SellerBadge
import pg.mcxus.app.ui.Tag
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx

fun maskPhone(phone: String): String = if (phone.length < 6) phone else phone.take(phone.length - 6).let { head ->
    "$head" + "•".repeat(4) + phone.takeLast(2)
}

@Composable
fun MeTab(nav: NavHostController) {
    val app = LocalApp.current
    val profile = rememberLoader(Unit) {
        val me = app.api.obj("/v1/me")
        me to app.api.obj("/v1/sellers/${me.str("id")}")
    }
    var editingServer by remember { mutableStateOf(false) }
    var signingOut by remember { mutableStateOf(false) }
    val m = profile.data?.first
    val s = profile.data?.second
    if (m != null && app.displayName.isEmpty()) app.displayName = m.str("display_name")

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).statusBarsPadding().padding(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Avatar(m?.str("display_name") ?: "Me", 68.dp, ring = Mx.Gold, key = app.session.userId ?: "")
            Column(Modifier.weight(1f)) {
                Text(m?.str("display_name")?.ifEmpty { "Set your name" } ?: (profile.error ?: "…"), fontSize = 21.sp, fontWeight = FontWeight.ExtraBold)
                Text(maskPhone(m?.str("phone") ?: app.session.phone), fontSize = 13.sp, color = Mx.Muted)
                Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    m?.let { Tag("Level ${it.optInt("kyc_tier")}", Mx.GreenSoft, Mx.GreenInk) }
                    s?.let { SellerBadge(it.str("badge")) }
                    if (m?.str("role")?.let { it != "user" } == true) Tag(m.str("role"))
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Stat(s?.optInt("completed_sales")?.toString() ?: "–", "Sales", Modifier.weight(1f))
            Stat(s?.str("rating")?.ifEmpty { null }?.let { "★ $it" } ?: "–", "Rating", Modifier.weight(1f))
            Stat(s?.optInt("active_listings")?.toString() ?: "–", "Listings", Modifier.weight(1f))
        }
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Mx.Navy).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Ic.Shield, null, tint = Mx.Gold, modifier = Modifier.size(34.dp))
            Column(Modifier.weight(1f)) {
                Text("Premium Privacy", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                Text("Hidden profile, disappearing status, no ads. Coming soon.", color = Mx.OnNavyMuted, fontSize = 12.sp)
            }
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Color.White)) {
            Row_(Ic.Edit, "Edit profile & my listings") { nav.navigate(Routes.PROFILE) }
            Row_(Ic.Receipt, "My orders") { nav.navigate(Routes.ORDERS) }
            Row_(Ic.Store, "Sell something") { nav.navigate(Routes.SELL) }
            var previews by remember { mutableStateOf(app.session.showPreviews) }
            Row_(Ic.Bell, "Notifications", if (previews) "Show text" else "Hide text", tag = "notif-previews") {
                previews = !previews
                app.session.showPreviews = previews
                app.say(if (previews) "Notifications show who wrote and the message" else "Notifications say only \"New message\"")
            }
            Row_(Ic.Lock, "Privacy", "E2E encrypted") { app.say("Chats are end-to-end encrypted with MLS. Verify a contact with ⋮ › Safety number in a chat.") }
            Row_(Ic.Server, "Server", app.session.server.removePrefix("http://").removePrefix("https://").take(22)) { editingServer = true }
            Row_(Ic.Logout, "Sign out", tag = "sign-out") { signingOut = true }
        }
        Text("McXus ${BuildConfig.VERSION_NAME} · open source (Apache-2.0)", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.padding(4.dp))
    }

    if (editingServer) {
        var value by remember { mutableStateOf(app.session.server) }
        AlertDialog(
            onDismissRequest = { editingServer = false },
            title = { Text("Server address") },
            text = { Field(value, { value = it }, "e.g. http://192.168.1.20:8000", keyboard = KeyboardType.Uri) },
            confirmButton = { TextButton(onClick = { app.session.server = value; editingServer = false; app.say("Saved. Restart the app to reconnect chat.") }) { Text("Save") } },
            dismissButton = { TextButton(onClick = { editingServer = false }) { Text("Cancel") } },
        )
    }
    if (signingOut) {
        AlertDialog(
            onDismissRequest = { signingOut = false },
            text = { Text("Sign out? Your encrypted chats stay on this phone and come back when you sign in again with the same number.") },
            confirmButton = { TextButton(onClick = { signingOut = false; app.signOut() }) { Text("Sign out") } },
            dismissButton = { TextButton(onClick = { signingOut = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier) {
    Column(modifier.clip(RoundedCornerShape(14.dp)).background(Color.White).padding(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, fontSize = 19.sp, fontWeight = FontWeight.ExtraBold)
        Text(label, fontSize = 12.sp, color = Mx.Muted)
    }
}

@Suppress("FunctionName")
@Composable
private fun Row_(icon: ImageVector, label: String, value: String = "", tag: String = label, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(52.dp).clickable(onClick = onClick).padding(horizontal = 14.dp).testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(32.dp).clip(RoundedCornerShape(10.dp)).background(Mx.Tint), contentAlignment = Alignment.Center) {
            Icon(icon, null, tint = Mx.Blue, modifier = Modifier.size(18.dp))
        }
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        Text(value, fontSize = 13.sp, color = Mx.Muted)
        Icon(Ic.Right, null, tint = Mx.Grey, modifier = Modifier.size(16.dp))
    }
    HorizontalDivider(color = Mx.LineSoft)
}
