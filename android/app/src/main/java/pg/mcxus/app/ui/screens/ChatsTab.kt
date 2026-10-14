package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.chat.Conversation
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Pill
import pg.mcxus.app.ui.RoundIcon
import pg.mcxus.app.ui.SellerBadge
import pg.mcxus.app.ui.StarLogo
import pg.mcxus.app.ui.initials
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

@Composable
fun ChatsTab(nav: NavHostController) {
    val app = LocalApp.current
    val engine = app.chat
    val conversations by (engine?.conversations ?: kotlinx.coroutines.flow.MutableStateFlow(emptyList())).collectAsState()
    val online by (engine?.online ?: kotlinx.coroutines.flow.MutableStateFlow(false)).collectAsState()
    var filter by rememberSaveable { mutableStateOf("all") }
    var searching by rememberSaveable { mutableStateOf(false) }
    var query by rememberSaveable { mutableStateOf("") }

    val unreadChats = conversations.count { it.unread > 0 }
    val shown = conversations.filter {
        when (filter) {
            "unread" -> it.unread > 0
            "sellers" -> it.listingId != null
            else -> true
        } && (query.isBlank() || it.peer.name.contains(query.trim(), ignoreCase = true))
    }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Row(
                Modifier.fillMaxWidth().statusBarsPadding().padding(start = 18.dp, end = 16.dp, top = 14.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                StarLogo(30.dp)
                Text("McXus", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                RoundIcon(Ic.Scan, "Add contact by number", onClick = { nav.navigate(Routes.NEW_CHAT) })
                RoundIcon(Ic.Search, "Search chats", onClick = { searching = !searching; if (!searching) query = "" })
            }
            if (searching) Field(query, { query = it }, "Search chats", modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))

            // Recent people (statuses arrive with Discover in M5).
            LazyRow(
                contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(14.dp),
                modifier = Modifier.padding(top = 4.dp, bottom = 10.dp),
            ) {
                item {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(62.dp)) {
                        Box {
                            Box(Modifier.size(58.dp).clip(CircleShape).background(Mx.Slate), contentAlignment = Alignment.Center) {
                                Text(initials(app.displayName.ifEmpty { "Me" }), color = Mx.Blue, fontWeight = FontWeight.Bold)
                            }
                            Box(
                                Modifier.align(Alignment.BottomEnd).size(22.dp).clip(CircleShape).background(Mx.Blue)
                                    .border(2.dp, Mx.Bg, CircleShape),
                                contentAlignment = Alignment.Center,
                            ) { Icon(Ic.Plus, null, tint = Color.White, modifier = Modifier.size(12.dp)) }
                        }
                        Text("My status", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.padding(top = 6.dp))
                    }
                }
                items(conversations.take(10), key = { "s" + it.id }) { c ->
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier.width(62.dp).clickable { nav.navigate(Routes.chat(c.id)) },
                    ) {
                        Box(
                            Modifier.size(58.dp).border(3.dp, if (c.unread > 0) Mx.Gold else Mx.ChipLine, CircleShape).padding(5.dp),
                        ) { Avatar(c.peer.name, 48.dp, key = c.peer.id) }
                        Text(
                            c.peer.name, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(top = 6.dp),
                        )
                    }
                }
            }

            Row(Modifier.padding(start = 16.dp, end = 16.dp, bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill("All", filter == "all", { filter = "all" })
                Pill(if (unreadChats > 0) "Unread $unreadChats" else "Unread", filter == "unread", { filter = "unread" })
                Pill("Sellers", filter == "sellers", { filter = "sellers" })
            }

            Column(
                Modifier.weight(1f).fillMaxWidth().clip(RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp)).background(Color.White),
            ) {
                if (!online) {
                    Text(
                        if (engine == null) "Starting encryption…" else "Connecting…",
                        Modifier.fillMaxWidth().background(Mx.GoldSoft).padding(6.dp),
                        color = Mx.GoldInk, fontSize = 12.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    )
                }
                LazyColumn(Modifier.fillMaxSize().testTag("chat-list")) {
                    if (shown.isEmpty()) {
                        item {
                            Empty(
                                if (conversations.isEmpty()) "No chats yet. Tap the gold button to message someone by phone number, or tap Chat on any listing."
                                else "Nothing here.",
                            )
                        }
                    }
                    items(shown, key = { it.id }) { ChatRow(it) { nav.navigate(Routes.chat(it.id)) } }
                    item {
                        Row(
                            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 96.dp),
                            horizontalArrangement = Arrangement.Center,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(Ic.Lock, null, tint = Mx.Muted, modifier = Modifier.size(14.dp))
                            Text(" Your personal messages are end-to-end encrypted", fontSize = 12.sp, color = Mx.Muted)
                        }
                    }
                }
            }
        }
        FloatingActionButton(
            onClick = { nav.navigate(Routes.NEW_CHAT) },
            containerColor = Mx.Gold, contentColor = Mx.Navy, shape = RoundedCornerShape(20.dp),
            modifier = Modifier.align(Alignment.BottomEnd).padding(18.dp).size(58.dp).testTag("new-chat"),
        ) { Icon(Ic.NewChat, contentDescription = "New chat", modifier = Modifier.size(26.dp)) }
    }
}

@Composable
private fun ChatRow(c: Conversation, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Avatar(c.peer.name, 50.dp, key = c.peer.id)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(c.peer.name, fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false))
                if (c.listingId != null) SellerBadge(c.peer.badge)
                Spacer(Modifier.weight(1f))
                Text(Format.chatTime(c.lastAt), fontSize = 12.sp, color = if (c.unread > 0) Mx.Blue else Mx.Muted)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (!c.encryptionReady) Icon(Ic.Lock, null, tint = Mx.Grey, modifier = Modifier.size(14.dp))
                Text(c.lastPreview, fontSize = 14.sp, color = Mx.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (c.unread > 0) {
                    Text(
                        c.unread.toString(),
                        Modifier.clip(RoundedCornerShape(11.dp)).background(Mx.Blue).padding(horizontal = 7.dp, vertical = 2.dp),
                        color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                    )
                }
            }
            Spacer(Modifier.height(2.dp))
        }
    }
}
