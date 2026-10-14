package pg.mcxus.app.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.SecureScreen
import pg.mcxus.app.back
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Card
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.Pill
import pg.mcxus.app.ui.PlaceCard
import pg.mcxus.app.ui.PlaceField
import pg.mcxus.app.util.Place
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images

@Composable
fun OrdersScreen(nav: NavHostController) {
    val app = LocalApp.current
    var asSeller by rememberSaveable { mutableStateOf(false) }
    val orders = rememberLoader(asSeller) { app.api.list("/v1/orders?as=${if (asSeller) "seller" else "buyer"}").objects() }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("My orders", onBack = { nav.back() }) {
            IconButton(onClick = { orders.reload() }) { Icon(Ic.Refresh, "Refresh", tint = Mx.Blue) }
        }
        Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill("Buying", !asSeller, { asSeller = false })
            Pill("Selling", asSeller, { asSeller = true })
        }
        val list = orders.data
        when {
            list == null && orders.error != null -> Empty(orders.error!!)
            list == null -> Loading()
            list.isEmpty() -> Empty(if (asSeller) "No sales yet." else "No purchases yet. Find something in Market.")
            else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(list, key = { it.str("id") }) { o ->
                    Card(Modifier.clickable { nav.navigate(Routes.order(o.str("id"))) }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(o.str("title"), fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), maxLines = 1)
                            Text(Format.kina(o.str("amount")), color = Mx.Blue, fontWeight = FontWeight.ExtraBold)
                        }
                        Text(Format.orderStatus(o.str("status"), asSeller), fontSize = 13.sp, color = Mx.Muted)
                        Text(Format.dateTime(o.str("created_at")), fontSize = 12.sp, color = Mx.Muted)
                    }
                }
            }
        }
    }
}

/** One order: the buyer's handover PIN + QR, the seller's PIN entry, and every escrow action. */
@Composable
fun OrderScreen(nav: NavHostController, orderId: String) {
    SecureScreen()
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val loader = rememberLoader(orderId, refresh) { app.api.obj("/v1/orders/$orderId") }
    var confirm by remember { mutableStateOf<Pair<String, () -> Unit>?>(null) }
    var busy by remember { mutableStateOf(false) }
    var pinInput by remember { mutableStateOf("") }
    var disputing by remember { mutableStateOf(false) }
    var rating by remember { mutableIntStateOf(5) }
    var comment by remember { mutableStateOf("") }
    var rated by remember { mutableStateOf(false) }
    var editingPlace by remember { mutableStateOf<Place?>(null) }

    fun act(action: String, body: JSONObject? = null) {
        busy = true
        app.launch(onDone = { busy = false }) {
            val r = app.api.post("/v1/orders/$orderId/$action", body, idempotent = action in listOf("pay", "confirm-receipt", "handover"))
            if (action == "pay") app.session.pins[orderId] = r.str("handover_pin")
            app.say("Done")
            refresh++
        }
    }

    Column(Modifier.fillMaxSize().background(Mx.Navy)) {
        Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start = 4.dp, end = 12.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Ic.Back, "Back", tint = Color.White) }
            Text("Order & handover", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.weight(1f))
            Icon(Ic.Lock, null, tint = Mx.OnNavyMuted, modifier = Modifier.size(14.dp))
            Text(" Screenshots blocked", color = Mx.OnNavyMuted, fontSize = 11.sp)
        }
        val o = loader.data
        Column(
            Modifier.weight(1f).padding(horizontal = 12.dp).clip(RoundedCornerShape(24.dp)).background(Color.White)
                .verticalScroll(rememberScrollState()).padding(18.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (o == null) {
                if (loader.error != null) Empty(loader.error!!) else Loading()
                return@Column
            }
            val status = o.str("status")
            val asSeller = o.str("seller_id") == app.session.userId
            Column(Modifier.fillMaxWidth()) {
                Text(o.str("title"), fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text("${Format.kina(o.str("amount"))} · qty ${o.optInt("quantity", 1)} · ${if (asSeller) "you are selling" else "you are buying"}",
                    fontSize = 13.sp, color = Mx.Muted)
            }
            Text(
                Format.orderStatus(status, asSeller),
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Mx.GoldSoft).padding(10.dp),
                color = Mx.GoldInk, fontWeight = FontWeight.Bold, fontSize = 14.sp, textAlign = TextAlign.Center,
            )
            if (status == "FUNDED") Format.minutesUntil(o.str("accept_deadline"))?.takeIf { it >= 0 }?.let {
                Text("$it min left for the seller to accept", fontSize = 13.sp, color = Mx.Muted)
            }
            if (status == "DISPATCHED") Text("Auto-release on ${Format.dateTime(o.str("auto_release_at"))} unless you report a problem.", fontSize = 13.sp, color = Mx.Muted, textAlign = TextAlign.Center)
            if (o.str("closed_at").isNotEmpty()) {
                Text("Fee ${Format.kina(o.str("fee_charged"))} · buyer refunded ${Format.kina(o.str("buyer_refunded"))} · seller paid ${Format.kina(o.str("seller_paid"))}",
                    fontSize = 12.sp, color = Mx.Muted, textAlign = TextAlign.Center)
            }

            val place = Place.from(o, "delivery_")
            val open = o.str("closed_at").isEmpty()
            val method = o.str("delivery_method").ifEmpty { "meetup" }
            val placeTitle = when (method) {
                "seller_delivers" -> "Seller delivers to"
                "courier" -> "Courier delivers to"
                "pickup" -> "Pick up at"
                else -> "Meet at"
            }
            if (place != null) {
                PlaceCard(placeTitle, place, action = if (open) ({
                    Text("Change place", color = Mx.Blue, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                        modifier = Modifier.padding(top = 4.dp).clickable { editingPlace = place }.testTag("change-place"))
                }) else null)
            } else if (open) {
                LineButton("Set the handover place", { editingPlace = Place() }, Modifier.fillMaxWidth())
            }

            if (!asSeller) {
                when (status) {
                    "CREATED" -> {
                        BigButton("Pay with Stars", busy = busy, onClick = { act("pay") })
                        LineButton("Cancel (free before paying)", { act("cancel") }, Modifier.fillMaxWidth())
                    }
                    "FUNDED", "ACCEPTED", "DISPATCHED" -> {
                        val pin = app.session.pins[orderId]
                        if (pin == null) {
                            BigButton("Show handover PIN", busy = busy, onClick = {
                                busy = true
                                app.launch(onDone = { busy = false }) {
                                    app.session.pins[orderId] = app.api.post("/v1/orders/$orderId/pin").str("handover_pin")
                                    refresh++
                                }
                            })
                        } else {
                            val qr = remember(pin) { Images.qr(Format.handoverQr(orderId, pin), 512).asImageBitmap() }
                            Image(qr, "Handover QR code", Modifier.size(196.dp))
                            Text("Handover PIN", fontSize = 12.sp, color = Mx.Muted)
                            Text(pin.chunked(3).joinToString(" "), fontSize = 40.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 6.sp,
                                color = Mx.Navy, modifier = Modifier.testTag("handover-pin"))
                            Text("Show this only when you have the item in your hands. The seller types the PIN and the Stars are released.",
                                fontSize = 13.sp, color = Mx.Muted, textAlign = TextAlign.Center)
                        }
                        if (status != "FUNDED") {
                            BigButton("I received it — release Stars", busy = busy, onClick = {
                                confirm = "Only confirm if you have the item. The seller gets the Stars now." to { act("confirm-receipt") }
                            })
                            LineButton("Problem with the item? Open a dispute", { disputing = true }, Modifier.fillMaxWidth())
                        }
                        if (status != "DISPATCHED") {
                            LineButton("Cancel order", {
                                confirm = "Cancelling after paying costs a 5% fee (minimum K2), shared by the seller and McXus. Cancel anyway?" to { act("cancel") }
                            }, Modifier.fillMaxWidth(), color = Mx.Red)
                        }
                    }
                    "RELEASED", "RESOLVED" -> if (!rated) {
                        Text("Rate the seller", fontWeight = FontWeight.Bold)
                        Row {
                            (1..5).forEach { n ->
                                Text(if (n <= rating) "★" else "☆", fontSize = 34.sp, color = Mx.Gold,
                                    modifier = Modifier.clickable { rating = n }.padding(4.dp))
                            }
                        }
                        Field(comment, { comment = it.take(500) }, "Comment (optional)")
                        BigButton("Send rating", busy = busy, onClick = {
                            busy = true
                            app.launch(onDone = { busy = false }) {
                                app.api.post("/v1/orders/$orderId/review", JSONObject().put("stars", rating).put("comment", comment))
                                rated = true
                                app.say("Thanks for rating")
                            }
                        })
                    }
                }
            } else {
                when (status) {
                    "FUNDED" -> {
                        BigButton("Accept order", busy = busy, onClick = { act("accept") })
                        LineButton("Reject (free within 20 minutes)", { act("reject") }, Modifier.fillMaxWidth(), color = Mx.Red)
                    }
                    "ACCEPTED", "DISPATCHED" -> {
                        Text("At handover, type the buyer's 6-digit PIN to receive your Stars.", fontSize = 14.sp, textAlign = TextAlign.Center)
                        Field(pinInput, { pinInput = it.filter(Char::isDigit).take(6) }, "Buyer's PIN", keyboard = KeyboardType.NumberPassword, tag = "seller-pin")
                        BigButton("Confirm handover", busy = busy, enabled = pinInput.length == 6, onClick = { act("handover", JSONObject().put("pin", pinInput)) })
                        if (status == "ACCEPTED") {
                            LineButton("Mark as sent (courier / delivery)", { act("dispatch") }, Modifier.fillMaxWidth())
                            LineButton("Cancel order", {
                                confirm = "Cancelling more than 25 minutes after payment costs you a 5% fee. Cancel?" to { act("cancel") }
                            }, Modifier.fillMaxWidth(), color = Mx.Red)
                        }
                    }
                }
            }
        }
        Box(Modifier.navigationBarsPadding().padding(10.dp))
    }

    confirm?.let { (text, run) ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            text = { Text(text) },
            confirmButton = { TextButton(onClick = { confirm = null; run() }) { Text("Yes") } },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("No") } },
        )
    }
    editingPlace?.let { start ->
        var draft by remember(start) { mutableStateOf(start) }
        AlertDialog(
            onDismissRequest = { editingPlace = null },
            title = { Text("Where to hand over") },
            text = { PlaceField("Handover place", draft, { draft = it }, hint = "The other person sees the change on this order.") },
            confirmButton = {
                TextButton(onClick = {
                    if (draft.isEmpty) return@TextButton app.say("Set a GPS point or type an address")
                    editingPlace = null
                    busy = true
                    app.launch(onDone = { busy = false }) {
                        app.api.post("/v1/orders/$orderId/delivery-location", draft.toJson())
                        app.say("Handover place updated")
                        refresh++
                    }
                }) { Text("Save") }
            },
            dismissButton = { TextButton(onClick = { editingPlace = null }) { Text("Cancel") } },
        )
    }
    if (disputing) {
        var reason by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { disputing = false },
            title = { Text("Report a problem") },
            text = { Field(reason, { reason = it.take(500) }, "What went wrong?", singleLine = false, minLines = 3) },
            confirmButton = {
                TextButton(onClick = {
                    disputing = false
                    act("dispute", JSONObject().put("reason", reason.ifBlank { "Problem with the item" }))
                }) { Text("Send") }
            },
            dismissButton = { TextButton(onClick = { disputing = false }) { Text("Cancel") } },
        )
    }
}
