package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.chat.Payload
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.PhotoButtons
import pg.mcxus.app.ui.Pill
import pg.mcxus.app.ui.PlaceCard
import pg.mcxus.app.ui.PlaceField
import pg.mcxus.app.util.Place
import pg.mcxus.app.ui.RemoteImage
import pg.mcxus.app.ui.RoundIcon
import pg.mcxus.app.ui.SellerBadge
import pg.mcxus.app.ui.StarsAmount
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ListingScreen(nav: NavHostController, listingId: String) {
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val loader = rememberLoader(listingId, refresh) { app.api.obj("/v1/listings/$listingId") }
    val item = loader.data ?: run {
        Column(Modifier.fillMaxSize().background(Mx.Bg)) {
            pg.mcxus.app.ui.Header("Listing", onBack = { nav.back() })
            if (loader.error != null) Empty(loader.error!!) else Loading()
        }
        return
    }
    val seller = item.getJSONObject("seller")
    val mine = seller.str("id") == app.session.userId
    val photos = item.getJSONArray("photos").objects()
    var buying by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var reporting by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().background(Color.White)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
            Box(Modifier.fillMaxWidth().height(330.dp).background(Mx.Slate)) {
                if (photos.isEmpty()) {
                    RemoteImage(null, Modifier.fillMaxSize())
                } else {
                    val pager = rememberPagerState { photos.size }
                    HorizontalPager(pager, Modifier.fillMaxSize()) { i -> RemoteImage(photos[i].str("url"), Modifier.fillMaxSize(), item.str("title")) }
                    Row(Modifier.align(Alignment.BottomCenter).padding(bottom = 30.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        repeat(photos.size) { i ->
                            Box(Modifier.height(6.dp).width(if (i == pager.currentPage) 18.dp else 6.dp).clip(CircleShape)
                                .background(if (i == pager.currentPage) Mx.Navy else Mx.Grey))
                        }
                    }
                }
                Row(Modifier.fillMaxWidth().statusBarsPadding().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    RoundIcon(Ic.Back, "Back", onClick = { nav.back() }, tint = Mx.Ink)
                    Box(Modifier.weight(1f))
                    Box {
                        RoundIcon(Ic.More, "More", onClick = { menu = true }, tint = Mx.Ink)
                        DropdownMenu(menu, onDismissRequest = { menu = false }) {
                            if (!mine) DropdownMenuItem(text = { Text("Report this listing") }, onClick = { menu = false; reporting = true })
                            if (mine) {
                                val status = item.str("status")
                                DropdownMenuItem(text = { Text(if (status == "active") "Pause listing" else "Make active") }, onClick = {
                                    menu = false
                                    app.launch { app.api.post("/v1/listings/$listingId/status", JSONObject().put("status", if (status == "active") "paused" else "active")); refresh++ }
                                })
                                DropdownMenuItem(text = { Text("Close listing (sold)") }, onClick = {
                                    menu = false
                                    app.launch { app.api.post("/v1/listings/$listingId/status", JSONObject().put("status", "closed")); refresh++ }
                                })
                            }
                        }
                    }
                }
            }
            Column(
                Modifier.offset(y = (-18).dp).clip(RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp)).background(Color.White)
                    .padding(start = 16.dp, end = 16.dp, top = 18.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Column {
                    StarsAmount(item.str("price"), big = true)
                    Text(item.str("title"), fontSize = 19.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
                    val qty = item.optInt("quantity_available")
                    Text(
                        listOf(place(item), if (qty > 0) "$qty available" else "Sold out").filter { it.isNotEmpty() }.joinToString(" · ") +
                            if (item.str("status") != "active") " · ${item.str("status")}" else "",
                        fontSize = 13.sp, color = Mx.Muted, modifier = Modifier.padding(top = 4.dp),
                    )
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    val tags = buildList {
                        Format.condition(item.str("condition")).takeIf { it != "—" }?.let(::add)
                        item.getJSONArray("delivery_options").let { d -> (0 until d.length()).forEach { add(Format.delivery(d.getString(it))) } }
                    }
                    tags.forEach {
                        Text(it, Modifier.clip(RoundedCornerShape(10.dp)).background(Color(0xFFEEF2F7)).padding(horizontal = 10.dp, vertical = 5.dp),
                            fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Mx.GoldSoft).padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Icon(Ic.Shield, null, tint = Mx.GoldInk, modifier = Modifier.size(22.dp))
                    Text(
                        buildAnnotatedString {
                            withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append("Escrow protected. ") }
                            append("Your Stars stay locked until you give the seller your handover PIN. First buyer to pay gets it.")
                        },
                        fontSize = 13.sp, lineHeight = 18.sp, color = Color(0xFF4A3105),
                    )
                }
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).border(1.dp, Mx.Line, RoundedCornerShape(14.dp)).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Avatar(seller.str("name"), 46.dp, key = seller.str("id"))
                    Column(Modifier.weight(1f)) {
                        Text(seller.str("name") + if (mine) " (you)" else "", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                        val rating = seller.str("rating")
                        Text(if (rating.isNotEmpty()) "★ $rating · ${seller.optInt("reviews")} reviews" else "No reviews yet", fontSize = 12.sp, color = Mx.Muted)
                    }
                    SellerBadge(seller.str("badge"))
                }
                Place.from(item.optJSONObject("meetup"))?.let { meet ->
                    PlaceCard("Meet-up / pickup point", meet)
                }
                if (item.str("description").isNotEmpty()) {
                    Text(item.str("description"), fontSize = 14.sp, lineHeight = 21.sp, color = Mx.Body)
                }
                if (mine && photos.size < 5) {
                    Text("Photos (${photos.size} of 5)", fontWeight = FontWeight.Bold)
                    PhotoButtons(listingId) { refresh++ }
                }
                Box(Modifier.height(8.dp))
            }
        }
        HorizontalDivider(color = Mx.Line)
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (mine) {
                LineButton("My orders", { nav.navigate(Routes.ORDERS) }, Modifier.weight(1f))
            } else {
                LineButton("Chat", modifier = Modifier.testTag("listing-chat"), enabled = !busy, onClick = {
                    val engine = app.chat ?: return@LineButton app.say("Encryption is still starting, try again in a second.", error = true)
                    busy = true
                    app.launch(onDone = { busy = false }) {
                        val conv = engine.open(seller.str("id"), listingId)
                        val thumb = photos.firstOrNull()?.str("thumb_url") ?: ""
                        if (engine.messages(conv).none { Payload.parse(it.payload).optString("id") == listingId }) {
                            // First time this listing is discussed: share its card so both sides see what it's about.
                            runCatching { engine.send(conv, Payload.listing(listingId, item.str("title"), item.str("price"), thumb)) }
                        }
                        nav.navigate(Routes.chat(conv))
                    }
                })
                BigButton(
                    "Buy with Stars", modifier = Modifier.weight(1f).testTag("buy"),
                    enabled = item.optInt("quantity_available") > 0 && item.str("status") == "active", busy = busy,
                    icon = { Icon(Ic.Star, null, tint = Mx.Gold, modifier = Modifier.size(20.dp)) },
                    onClick = { buying = true },
                )
            }
        }
    }

    if (buying) BuyDialog(item, onDismiss = { buying = false }) { qty, delivery ->
        buying = false
        busy = true
        app.launch(onDone = { busy = false }) {
            val order = app.api.post(
                "/v1/listings/$listingId/buy", JSONObject().put("quantity", qty).put("delivery", delivery), idempotent = true,
            )
            val orderId = order.getString("id")
            val paid = app.api.post("/v1/orders/$orderId/pay", idempotent = true)
            app.session.pins[orderId] = paid.str("handover_pin")
            // Tell the seller in the encrypted chat (best effort: the order itself is already safe in escrow).
            app.chat?.let { engine ->
                runCatching {
                    val conv = engine.open(seller.str("id"), listingId)
                    engine.send(conv, Payload.order(orderId, item.str("title"), order.str("amount")))
                }
            }
            app.say("Paid. Your Stars are held in escrow.")
            nav.navigate(Routes.order(orderId))
        }
    }
    if (reporting) ReportDialog(onDismiss = { reporting = false }) { reason ->
        reporting = false
        app.launch { app.api.post("/v1/listings/$listingId/report", JSONObject().put("reason", reason)); app.say("Thanks. A moderator will check it.") }
    }
}

/** Quantity, how the item reaches the buyer, and where: GPS point first, landmark/address second. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BuyDialog(item: JSONObject, onDismiss: () -> Unit, onConfirm: (Int, JSONObject) -> Unit) {
    val app = LocalApp.current
    var qty by remember { mutableIntStateOf(1) }
    val options = item.getJSONArray("delivery_options").let { d -> (0 until d.length()).map { d.getString(it) } }
    var method by remember { mutableStateOf(options.firstOrNull() ?: "meetup") }
    val sellerPoint = Place.from(item.optJSONObject("meetup"))
    var place by remember { mutableStateOf(Place()) }
    var otherPlace by remember { mutableStateOf(false) }
    val toBuyer = method == "seller_delivers" || method == "courier"
    val max = item.optInt("quantity_available", 1)
    val total = java.math.BigDecimal(item.str("price")).multiply(java.math.BigDecimal(qty)).setScale(2).toPlainString()
    androidx.compose.ui.window.Dialog(onDismissRequest = onDismiss, properties = androidx.compose.ui.window.DialogProperties(usePlatformDefaultWidth = false)) {
        Column(
            Modifier.fillMaxWidth().padding(16.dp).clip(RoundedCornerShape(24.dp)).background(Mx.Bg)
                .verticalScroll(rememberScrollState()).padding(18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Buy with Stars", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold)
            Text(item.str("title"), fontWeight = FontWeight.Bold)
            if (max > 1) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Quantity", modifier = Modifier.weight(1f))
                    TextButton(onClick = { if (qty > 1) qty-- }) { Text("–", fontSize = 22.sp) }
                    Text("$qty", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    TextButton(onClick = { if (qty < max) qty++ }) { Text("+", fontSize = 22.sp) }
                }
            }
            Text("How do you get it?", fontWeight = FontWeight.Bold)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                options.forEach { o -> Pill(Format.delivery(o), method == o, { method = o }) }
            }
            when {
                toBuyer -> PlaceField(
                    "Deliver to", place, { place = it },
                    hint = "The seller or courier gets directions to this point. Add a landmark they can ask for.",
                )
                otherPlace || sellerPoint == null -> PlaceField(
                    "Suggest a meeting place", place, { place = it },
                    hint = if (sellerPoint == null) "The seller did not set a point. Suggest a busy public place." else "The seller sees your suggestion on the order.",
                )
                else -> {
                    PlaceCard("Seller's meet-up point", sellerPoint)
                    TextButton(onClick = { otherPlace = true }) { Text("Suggest another place") }
                }
            }
            Text("Total ${Format.price(total)}", fontWeight = FontWeight.ExtraBold, color = Mx.Blue)
            Text(
                "Your Stars are held in escrow. The seller has 20 minutes to accept. Cancelling after you pay costs 5% (minimum K2).",
                fontSize = 13.sp, color = Mx.Muted,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                LineButton("Cancel", onDismiss, Modifier.weight(1f))
                BigButton("Pay ${Format.kina(total)}", modifier = Modifier.weight(1.4f).testTag("confirm-buy"), onClick = {
                    val needsPlace = toBuyer || sellerPoint == null && method == "meetup"
                    when {
                        needsPlace && place.isEmpty -> app.say(if (toBuyer) "Set where to deliver: your location, the map, or an address" else "Suggest where to meet", error = true)
                        place.hasPoint && !place.inPng -> app.say("That point is outside Papua New Guinea", error = true)
                        else -> {
                            val delivery = JSONObject().put("method", method)
                            if (!place.isEmpty) {
                                delivery.put("latitude", place.latitude ?: JSONObject.NULL).put("longitude", place.longitude ?: JSONObject.NULL)
                                    .put("address", place.address.trim())
                            }
                            onConfirm(qty, delivery)
                        }
                    }
                })
            }
        }
    }
}

@Composable
private fun ReportDialog(onDismiss: () -> Unit, onPick: (String) -> Unit) {
    val reasons = listOf("prohibited" to "Not allowed on McXus", "scam" to "Looks like a scam", "wrong_category" to "Wrong category",
        "offensive" to "Offensive", "other" to "Something else")
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Report listing") },
        text = {
            Column {
                reasons.forEach { (code, label) ->
                    TextButton(onClick = { onPick(code) }, modifier = Modifier.fillMaxWidth()) { Text(label, modifier = Modifier.fillMaxWidth()) }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
