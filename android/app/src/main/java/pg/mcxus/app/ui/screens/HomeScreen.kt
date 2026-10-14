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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import pg.mcxus.app.LocalApp
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.theme.Mx

private data class Tab(val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab("Chats", Ic.Chat), Tab("Discover", Ic.Discover), Tab("Market", Ic.Market), Tab("Wallet", Ic.Wallet), Tab("Me", Ic.Me),
)

/** The five main tabs: Chats · Discover · Market · Wallet · Me. */
@Composable
fun HomeScreen(nav: NavHostController, initialTab: Int = 0) {
    var tab by rememberSaveable(initialTab) { mutableIntStateOf(initialTab) }
    val chat = LocalApp.current.chat
    val conversations = chat?.conversations?.collectAsState()?.value.orEmpty()
    val unread = conversations.sumOf { it.unread }
    // Android 13+: ask once for permission to show new-message notifications.
    val context = androidx.compose.ui.platform.LocalContext.current
    val askNotifications = androidx.activity.compose.rememberLauncherForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.RequestPermission(),
    ) { }
    androidx.compose.runtime.LaunchedEffect(Unit) {
        val prefs = context.getSharedPreferences("mcxus", android.content.Context.MODE_PRIVATE)
        if (android.os.Build.VERSION.SDK_INT >= 33 && !pg.mcxus.app.Notifier.allowed(context) && !prefs.getBoolean("asked_notifications", false)) {
            prefs.edit().putBoolean("asked_notifications", true).apply()
            askNotifications.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Box(Modifier.weight(1f)) {
            when (tab) {
                0 -> ChatsTab(nav)
                1 -> DiscoverTab(nav, openMarket = { tab = 2 })
                2 -> MarketTab(nav)
                3 -> WalletTab(nav)
                else -> MeTab(nav)
            }
        }
        HorizontalDivider(color = Mx.Line)
        Row(Modifier.fillMaxWidth().background(Color.White).navigationBarsPadding().padding(top = 6.dp, bottom = 8.dp)) {
            tabs.forEachIndexed { i, t ->
                val on = i == tab
                Column(
                    Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).clickable { tab = i }.testTag("tab-${t.label}"),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box {
                        Box(
                            Modifier.width(56.dp).height(30.dp).clip(RoundedCornerShape(15.dp))
                                .background(if (on) Mx.GoldSoft else Color.Transparent),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(t.icon, contentDescription = null, tint = if (on) Mx.Navy else Mx.Muted, modifier = Modifier.size(22.dp))
                        }
                        if (i == 0 && unread > 0) {
                            Text(
                                if (unread > 99) "99+" else unread.toString(),
                                modifier = Modifier.align(Alignment.TopEnd).clip(RoundedCornerShape(9.dp)).background(Mx.Blue)
                                    .padding(horizontal = 5.dp),
                                color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Text(
                        t.label, fontSize = 11.sp, color = if (on) Mx.Navy else Mx.Muted,
                        fontWeight = if (on) FontWeight.Bold else FontWeight.Medium, modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }
    }
}

@Composable
fun SheetDivider() = HorizontalDivider(color = Mx.LineSoft)

