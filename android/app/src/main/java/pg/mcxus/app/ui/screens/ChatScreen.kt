package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import kotlinx.coroutines.delay
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.chat.LocalMessage
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.chat.Readiness
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.PlaceField
import pg.mcxus.app.util.Place
import pg.mcxus.app.ui.RemoteImage
import pg.mcxus.app.ui.StarLogo
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Jakarta
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

@Composable
fun ChatScreen(nav: NavHostController, conversationId: String) {
    val app = LocalApp.current
    val engine = app.chat ?: run { Loading(); return }
    val conversations by engine.conversations.collectAsState()
    val version by engine.version.collectAsState()
    val conv = conversations.firstOrNull { it.id == conversationId }
    var readiness by remember { mutableStateOf<Readiness>(Readiness.Waiting("Securing this chat…")) }
    var draft by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var safety by remember { mutableStateOf<String?>(null) }
    var sharing by remember { mutableStateOf(false) }
    var attach by remember { mutableStateOf(false) }
    var sharingPlace by remember { mutableStateOf(false) }
    val messages = remember(version, conversationId) { engine.messages(conversationId) }
    val list = rememberLazyListState()

    LaunchedEffect(conversationId, conv != null) {
        if (conv == null) return@LaunchedEffect
        while (true) {
            readiness = try {
                engine.ensureReady(conversationId)
            } catch (e: Exception) {
                Readiness.Waiting(app.explain(e))
            }
            if (readiness !is Readiness.Waiting) break
            delay(2_000)
        }
    }
    LaunchedEffect(messages.size) {
        if (messages.any { it.unread }) engine.markRead(conversationId)
        if (messages.isNotEmpty()) list.animateScrollToItem(messages.size)
    }

    fun send(payload: String, after: () -> Unit = {}) {
        sending = true
        app.launch(onDone = { sending = false }) {
            if (engine.send(conversationId, payload)) after() else app.say("This chat is not ready yet — try again in a moment.")
        }
    }

    Column(Modifier.fillMaxSize().background(Mx.ChatBg)) {
        // Header (navy, like the design)
        Row(
            Modifier.fillMaxWidth().background(Mx.Navy).statusBarsPadding().padding(start = 4.dp, end = 6.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            IconButton(onClick = { nav.back() }) { Icon(Ic.Back, "Back to chats", tint = Color.White) }
            Avatar(conv?.peer?.name ?: "?", 40.dp, ring = Mx.Gold, key = conv?.peer?.id ?: "")
            Column(Modifier.weight(1f)) {
                Text(conv?.peer?.name ?: "Chat", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 16.sp, maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
                val sub = buildList {
                    conv?.peer?.badge?.takeIf { it.isNotEmpty() && it != "new_seller" }?.let { add(Format.badge(it)) }
                    conv?.peer?.rating?.let { add("★ $it") }
                    add(if (readiness == Readiness.Ready) "encrypted" else "securing…")
                }.joinToString(" · ")
                Text(sub, color = Mx.OnNavyMuted, fontSize = 12.sp, maxLines = 1)
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Ic.More, "More options", tint = Color.White) }
                DropdownMenu(menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(text = { Text("Verify encryption (safety number)") }, onClick = {
                        menu = false
                        safety = engine.safetyNumber(conversationId) ?: "Not available until the chat is set up."
                    })
                    DropdownMenuItem(text = { Text("My orders") }, onClick = { menu = false; nav.navigate(Routes.ORDERS) })
                }
            }
        }

        LazyColumn(
            state = list,
            modifier = Modifier.weight(1f).fillMaxWidth().testTag("messages"),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Row(
                        Modifier.widthIn(max = 300.dp).clip(RoundedCornerShape(10.dp)).background(Mx.GoldSoft).padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Ic.Lock, null, tint = Mx.GoldInk, modifier = Modifier.size(14.dp))
                        Text(
                            " End-to-end encrypted. Pay only inside McXus to stay protected.",
                            color = Mx.GoldInk, fontSize = 12.sp, textAlign = TextAlign.Center,
                        )
                    }
                }
            }
            when (val r = readiness) {
                is Readiness.Waiting -> item { SystemLine(r.why) }
                is Readiness.Failed -> item { SystemLine(r.why) }
                Readiness.Ready -> Unit
            }
            items(messages, key = { it.localId }) { m -> MessageItem(m, nav, version) }
        }

        // Composer
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(start = 10.dp, end = 10.dp, top = 6.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                Modifier.weight(1f).clip(RoundedCornerShape(24.dp)).background(Color.White).padding(start = 4.dp, end = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box {
                    IconButton(onClick = { attach = true }, modifier = Modifier.testTag("attach")) {
                        Icon(Ic.Plus, "Share a listing or a location", tint = Mx.Muted)
                    }
                    DropdownMenu(attach, onDismissRequest = { attach = false }) {
                        DropdownMenuItem(
                            text = { Text("Share a location (meet / deliver here)") },
                            leadingIcon = { Icon(Ic.Pin, null, tint = Mx.Blue) },
                            onClick = { attach = false; sharingPlace = true },
                        )
                        DropdownMenuItem(
                            text = { Text("Share one of my listings") },
                            leadingIcon = { Icon(Ic.Market, null, tint = Mx.Blue) },
                            onClick = { attach = false; sharing = true },
                        )
                    }
                }
                BasicTextField(
                    value = draft,
                    onValueChange = { draft = it.take(4000) },
                    textStyle = TextStyle(fontFamily = Jakarta, fontSize = 15.sp, color = Mx.Ink),
                    cursorBrush = SolidColor(Mx.Blue),
                    maxLines = 5,
                    modifier = Modifier.weight(1f).padding(vertical = 12.dp).testTag("composer"),
                    decorationBox = { inner ->
                        if (draft.isEmpty()) Text("Message", color = Mx.Grey, fontSize = 15.sp)
                        inner()
                    },
                )
                Row(
                    Modifier.clip(RoundedCornerShape(18.dp)).background(Mx.GoldSoft).clickable {
                        val listing = conv?.listingId
                        if (listing != null) nav.navigate(Routes.listing(listing))
                        else app.say("Open one of ${conv?.peer?.name ?: "their"} listings and tap Buy with Stars — payment stays in escrow.")
                    }.padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Ic.Star, null, tint = Mx.GoldDeep, modifier = Modifier.size(16.dp))
                    Text(" Pay", color = Mx.GoldInk, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                }
            }
            IconButton(
                onClick = { val text = draft.trim(); if (text.isNotEmpty()) send(Payload.text(text)) { draft = "" } },
                enabled = !sending && draft.isNotBlank() && readiness == Readiness.Ready,
                modifier = Modifier.size(48.dp).clip(CircleShape).background(if (draft.isNotBlank()) Mx.Blue else Mx.Grey).testTag("send"),
            ) { Icon(Ic.Send, "Send", tint = Color.White, modifier = Modifier.size(22.dp)) }
        }
    }

    safety?.let { number ->
        AlertDialog(
            onDismissRequest = { safety = null },
            confirmButton = { TextButton(onClick = { safety = null }) { Text("Done") } },
            title = { Text("Safety number") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Compare these numbers with ${conv?.peer?.name ?: "the other person"} in person or on a call. If they match, nobody is in the middle.")
                    Text(number.chunked(24).joinToString("\n"), fontWeight = FontWeight.Bold, fontSize = 16.sp, letterSpacing = 1.sp)
                }
            },
        )
    }
    if (sharingPlace) {
        var draft by remember { mutableStateOf(Place()) }
        AlertDialog(
            onDismissRequest = { sharingPlace = false },
            title = { Text("Share a location") },
            text = {
                PlaceField("Meet or deliver here", draft, { draft = it }, requirePng = false,
                    hint = "Only you and ${conv?.peer?.name ?: "this person"} can see it (end-to-end encrypted).")
            },
            confirmButton = {
                TextButton(onClick = {
                    if (draft.isEmpty) return@TextButton app.say("Use your location, the map, or type a landmark")
                    sharingPlace = false
                    send(Payload.location(draft))
                }, modifier = Modifier.testTag("send-location")) { Text("Send") }
            },
            dismissButton = { TextButton(onClick = { sharingPlace = false }) { Text("Cancel") } },
        )
    }
    if (sharing) ShareListingDialog(onDismiss = { sharing = false }) { item ->
        sharing = false
        val thumb = item.optJSONArray("photos")?.objects()?.firstOrNull()?.str("thumb_url") ?: ""
        send(Payload.listing(item.str("id"), item.str("title"), item.str("price"), thumb))
    }
}

@Composable
private fun SystemLine(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Text(
            text, Modifier.clip(RoundedCornerShape(8.dp)).background(Color.White).padding(horizontal = 10.dp, vertical = 4.dp),
            color = Mx.Muted, fontSize = 12.sp, textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun MessageItem(m: LocalMessage, nav: NavHostController, version: Long) {
    val p = Payload.parse(m.payload)
    when (p.optString("t")) {
        "system" -> SystemLine(p.optString("body"))
        "listing" -> Side(m.mine) {
            Column(
                Modifier.width(250.dp).clip(RoundedCornerShape(16.dp)).background(Color.White).border(1.dp, Mx.Field, RoundedCornerShape(16.dp))
                    .clickable { nav.navigate(Routes.listing(p.optString("id"))) },
            ) {
                RemoteImage(p.optString("thumb"), Modifier.fillMaxWidth().height(110.dp))
                Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
                    Text(p.optString("title"), fontWeight = FontWeight.Bold, fontSize = 14.sp, maxLines = 2)
                    Text(Format.kina(p.optString("price")) + " · " + p.optString("price").removeSuffix(".00") + " Stars",
                        color = Mx.Blue, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
                    Text("Escrow protected · " + Format.clock(m.at), color = Mx.Muted, fontSize = 12.sp)
                }
            }
        }
        "order" -> Side(m.mine) { OrderCard(p, nav, version) }
        "location" -> Side(m.mine) {
            val place = Place.from(p) ?: Place(address = "Location")
            val context = androidx.compose.ui.platform.LocalContext.current
            Column(
                Modifier.width(260.dp).clip(RoundedCornerShape(16.dp)).background(Color.White).border(1.dp, Mx.Field, RoundedCornerShape(16.dp)),
            ) {
                Row(
                    Modifier.fillMaxWidth().background(Mx.Navy).padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Ic.PinSolid, null, tint = Mx.Gold, modifier = Modifier.size(22.dp))
                    Text("  " + if (m.mine) "You shared a place" else "Meet / deliver here", color = Color.White,
                        fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(place.address.ifBlank { "GPS point" }, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    if (place.hasPoint) Text(place.coordinates(), fontSize = 12.sp, color = Mx.Muted)
                    Box(
                        Modifier.padding(top = 6.dp).fillMaxWidth().height(40.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Blue)
                            .clickable { pg.mcxus.app.util.Places.openInMaps(context, place, place.address.ifBlank { "Meet here" }) },
                        contentAlignment = Alignment.Center,
                    ) { Text("Directions", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp) }
                    Text(Format.clock(m.at), fontSize = 11.sp, color = Mx.Muted, modifier = Modifier.align(Alignment.End))
                }
            }
        }
        else -> Side(m.mine) {
            val shape = if (m.mine) RoundedCornerShape(16.dp, 16.dp, 4.dp, 16.dp) else RoundedCornerShape(16.dp, 16.dp, 16.dp, 4.dp)
            Column(
                Modifier.widthIn(max = 290.dp).clip(shape).background(if (m.mine) Mx.Blue else Color.White)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
            ) {
                Text(p.optString("body"), color = if (m.mine) Color.White else Mx.Ink, fontSize = 15.sp, lineHeight = 20.sp)
                Row(Modifier.align(Alignment.End), verticalAlignment = Alignment.CenterVertically) {
                    Text(Format.clock(m.at), color = if (m.mine) Mx.OnNavyMuted else Mx.Muted, fontSize = 11.sp)
                    if (m.mine) Icon(Ic.Check, "Sent", tint = Mx.OnNavyMuted, modifier = Modifier.padding(start = 3.dp).size(13.dp))
                }
            }
        }
    }
}

@Composable
private fun Side(mine: Boolean, content: @Composable () -> Unit) {
    Box(Modifier.fillMaxWidth(), contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart) { content() }
}

/** Live escrow card for an order shared in the chat (status is fetched from the server). */
@Composable
private fun OrderCard(p: JSONObject, nav: NavHostController, version: Long) {
    val app = LocalApp.current
    val id = p.optString("id")
    val order = rememberLoader(id, version) { app.api.obj("/v1/orders/$id") }
    val o = order.data
    val status = o?.str("status") ?: ""
    val asSeller = o?.str("seller_id") == app.session.userId
    Column(
        Modifier.width(280.dp).clip(RoundedCornerShape(16.dp)).background(Color.White).border(2.dp, Mx.Gold, RoundedCornerShape(16.dp))
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StarLogo(26.dp)
            Column(Modifier.weight(1f)) {
                Text("${Format.kina(p.optString("amount"))} in escrow", fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
                Text(p.optString("title"), color = Mx.Muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        if (o == null) {
            Text(order.error ?: "Loading order…", fontSize = 12.sp, color = Mx.Muted)
        } else {
            val paid = status !in listOf("CREATED")
            val accepted = status in listOf("ACCEPTED", "DISPATCHED", "RELEASED", "RESOLVED")
            val done = status in listOf("RELEASED", "RESOLVED")
            val mins = Format.minutesUntil(o.str("accept_deadline"))
            Step(paid, current = !paid, "Paid " + Format.dateTime(o.str("funded_at")).takeLast(5))
            Step(accepted, current = status == "FUNDED", if (status == "FUNDED" && mins != null && mins >= 0) "Seller accepts · $mins min left" else "Seller accepts")
            Step(done, current = accepted && !done, "Handover with the buyer's PIN")
            Text(Format.orderStatus(status, asSeller), fontSize = 12.sp, color = Mx.Muted)
        }
        Box(
            Modifier.fillMaxWidth().height(44.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Navy).clickable { nav.navigate(Routes.order(id)) },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                when {
                    asSeller && status == "FUNDED" -> "Accept or reject"
                    asSeller && status in listOf("ACCEPTED", "DISPATCHED") -> "Enter buyer's PIN"
                    !asSeller && status in listOf("FUNDED", "ACCEPTED", "DISPATCHED") -> "Show handover PIN"
                    else -> "Open order"
                },
                color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp,
            )
        }
    }
}

@Composable
private fun Step(done: Boolean, current: Boolean, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        val m = Modifier.size(18.dp).clip(CircleShape)
        if (done) {
            Box(m.background(Mx.Green), contentAlignment = Alignment.Center) {
                Icon(Ic.Check, null, tint = Color.White, modifier = Modifier.size(11.dp))
            }
        } else {
            Box(m.border(2.dp, if (current) Mx.Gold else Mx.ChipLine, CircleShape))
        }
        Text(label, fontSize = 13.sp, fontWeight = if (current) FontWeight.Bold else FontWeight.Normal, color = if (done || current) Mx.Ink else Mx.Muted)
    }
}

@Composable
private fun ShareListingDialog(onDismiss: () -> Unit, onPick: (JSONObject) -> Unit) {
    val app = LocalApp.current
    val mine = rememberLoader(Unit) { app.api.list("/v1/me/listings").objects().filter { it.str("status") == "active" } }
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close") } },
        title = { Text("Share a listing") },
        text = {
            val items = mine.data
            when {
                items == null -> Text(mine.error ?: "Loading…")
                items.isEmpty() -> Text("You have no active listings. Tap Sell in Market to add one.")
                else -> LazyColumn(Modifier.height(320.dp)) {
                    items(items, key = { it.str("id") }) { item ->
                        Row(
                            Modifier.fillMaxWidth().clickable { onPick(item) }.padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            RemoteImage(item.optJSONArray("photos")?.objects()?.firstOrNull()?.str("thumb_url"),
                                Modifier.size(48.dp).clip(RoundedCornerShape(10.dp)))
                            Column(Modifier.weight(1f)) {
                                Text(item.str("title"), fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(Format.kina(item.str("price")), color = Mx.Blue, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        },
    )
}
