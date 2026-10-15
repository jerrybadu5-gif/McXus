package pg.mcxus.app.ui.screens

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.back
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Card
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format
import pg.mcxus.app.util.Images
import java.math.BigDecimal

/**
 * A dispute on an order (ADR 0011), for the buyer or the seller:
 * 1. negotiate (3 days): offers "you get back K__", accept/reject; or ask for a mediator now;
 * 2. a mediator decides (5 PNG working days) from both sides' statements and photos;
 * 3. accept the decision, or appeal once within 3 days; a senior staff member's decision is final.
 * The server says which actions are allowed now ("actions"); the screen shows only those.
 */
@Composable
fun DisputeScreen(nav: NavHostController, orderId: String) {
    val app = LocalApp.current
    val context = LocalContext.current
    var refresh by remember { mutableIntStateOf(0) }
    val loader = rememberLoader(orderId, refresh) { app.api.obj("/v1/disputes/$orderId") }
    var busy by remember { mutableStateOf(false) }
    var dialog by remember { mutableStateOf<String?>(null) } // offer | statement | appeal | photo
    var cameraUri by remember { mutableStateOf<android.net.Uri?>(null) }

    // The other person or a mediator may act at any time: check again every 20 seconds while open.
    LaunchedEffect(orderId) {
        while (true) {
            delay(20_000)
            if (loader.data?.str("stage") != "resolved") loader.reload()
        }
    }

    fun post(path: String, body: JSONObject? = null, done: String) {
        busy = true
        app.launch(onDone = { busy = false }) {
            loader.data = app.api.post("/v1/disputes/$orderId/$path", body)
            app.say(done)
        }
    }

    fun sendPhoto(uri: android.net.Uri) {
        busy = true
        app.launch(onDone = { busy = false }) {
            val jpeg = withContext(Dispatchers.Default) { Images.prepareUpload(context.contentResolver, uri, maxPx = 1600, quality = 80) }
            loader.data = JSONObject(app.api.upload("/v1/disputes/$orderId/photos", jpeg).toString())
            app.say("Photo added. The other person and the mediator can see it.")
        }
    }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { it?.let(::sendPhoto) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) cameraUri?.let(::sendPhoto) }

    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("Dispute", onBack = { nav.back() })
        val d = loader.data
        if (d == null) {
            if (loader.error != null) Empty(loader.error!!) else Loading()
            return@Column
        }
        val stage = d.str("stage")
        val you = d.str("you")
        val actions = d.optJSONArray("actions")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty().toSet()
        val amount = d.str("amount")
        val other = if (you == "buyer") "seller" else "buyer"
        val otherName = d.optJSONObject(other)?.str("name").orEmpty()

        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Card {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(d.str("title"), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = Mx.Ink)
                        Text("You are the $you · with $otherName", fontSize = 12.sp, color = Mx.Muted)
                    }
                    Text(Format.kina(amount), fontWeight = FontWeight.ExtraBold, fontSize = 20.sp, color = Mx.Navy)
                }
                Spacer(Modifier.height(10.dp))
                StageTrack(d)
                Spacer(Modifier.height(10.dp))
                Text(explain(d, you, otherName), fontSize = 13.sp, lineHeight = 18.sp, color = Mx.Body, modifier = Modifier.testTag("dispute-explain"))
            }

            d.optJSONObject("resolution")?.let { r ->
                Card(Modifier.border(1.dp, Mx.Green.copy(alpha = 0.35f), RoundedCornerShape(18.dp))) {
                    Text("Closed", fontWeight = FontWeight.Bold, color = Mx.Green)
                    Text("Buyer got back ${Format.kina(r.str("buyer_refund"))}; seller ${Format.kina(r.str("seller_gets"))} before the 3% escrow fee.",
                        fontSize = 14.sp, color = Mx.Ink)
                    if (r.str("note").isNotEmpty()) Text(r.str("note"), fontSize = 12.sp, color = Mx.Muted)
                }
            }

            d.optJSONObject("decision")?.takeIf { stage == "decided" || stage == "appeal" }?.let { dec ->
                Card(Modifier.border(1.dp, Mx.Gold, RoundedCornerShape(18.dp))) {
                    Text("The mediator decided", fontWeight = FontWeight.Bold, color = Mx.Ink)
                    Text("Buyer gets back ${Format.kina(dec.str("buyer_refund"))} · seller gets ${Format.kina(minus(amount, dec.str("buyer_refund")))}",
                        fontWeight = FontWeight.Bold, fontSize = 15.sp, color = Mx.Navy, modifier = Modifier.testTag("decision"))
                    Text(dec.str("note"), fontSize = 13.sp, color = Mx.Body)
                    if (stage == "decided") {
                        Text("Final on ${Format.dateTime(d.str("appeal_until"))} unless someone appeals.", fontSize = 12.sp, color = Mx.Muted)
                    }
                    if ("accept_decision" in actions) {
                        Spacer(Modifier.height(8.dp))
                        BigButton("Accept the decision", busy = busy, onClick = { post("accept-decision", null, "You accepted. It is final when the $other accepts or the 3 days end.") })
                    }
                    if ("appeal" in actions) {
                        Spacer(Modifier.height(6.dp))
                        LineButton("Appeal (once)", { dialog = "appeal" }, Modifier.fillMaxWidth(), color = Mx.Red)
                    }
                }
            }

            // Offers
            val offers = d.optJSONArray("offers")?.objects().orEmpty()
            if (offers.isNotEmpty() || "offer" in actions) {
                Text("Offers", fontWeight = FontWeight.Bold, color = Mx.Ink, modifier = Modifier.padding(top = 4.dp))
                offers.reversed().forEach { o ->
                    val mine = o.optBoolean("mine")
                    val open = o.str("status") == "open"
                    Card {
                        Text(
                            "${if (mine) "You" else "The $other"} offered: buyer gets back ${Format.kina(o.str("buyer_refund"))}",
                            fontWeight = FontWeight.Bold, color = Mx.Ink, fontSize = 14.sp,
                        )
                        Text("Seller gets ${Format.kina(minus(amount, o.str("buyer_refund")))} · ${offerStatus(o.str("status"), mine)}", fontSize = 12.sp, color = Mx.Muted)
                        if (o.str("note").isNotEmpty()) Text(o.str("note"), fontSize = 13.sp, color = Mx.Body)
                        if (open && "offer" in actions) {
                            Spacer(Modifier.height(8.dp))
                            if (mine) {
                                LineButton("Withdraw my offer", { post("offers/${o.str("id")}", JSONObject().put("accept", false), "Offer withdrawn") }, Modifier.fillMaxWidth())
                            } else {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    LineButton("Reject", { post("offers/${o.str("id")}", JSONObject().put("accept", false), "Offer rejected") }, Modifier.weight(1f), color = Mx.Red)
                                    BigButton("Accept", busy = busy, modifier = Modifier.weight(1f).testTag("accept-offer"),
                                        onClick = { post("offers/${o.str("id")}", JSONObject().put("accept", true), "Agreed. The Stars have moved.") })
                                }
                            }
                        }
                    }
                }
                if ("offer" in actions) LineButton("Make an offer", { dialog = "offer" }, Modifier.fillMaxWidth().testTag("make-offer"))
            }
            if ("escalate" in actions) {
                LineButton("Ask a mediator now", { post("escalate", null, "A mediator will decide within 5 working days.") }, Modifier.fillMaxWidth())
            }

            // Evidence
            Text("Statements and photos", fontWeight = FontWeight.Bold, color = Mx.Ink, modifier = Modifier.padding(top = 4.dp))
            Text("The $other and the mediator see everything here. Photos lose their location data when you add them.", fontSize = 12.sp, color = Mx.Muted)
            d.optJSONArray("evidence")?.objects().orEmpty().forEach { e ->
                val mine = e.optBoolean("mine")
                Card(Modifier.padding(start = if (mine) 28.dp else 0.dp, end = if (mine) 0.dp else 28.dp)) {
                    Text(if (mine) "You · ${Format.dateTime(e.str("at"))}" else "The ${e.str("by")} · ${Format.dateTime(e.str("at"))}", fontSize = 11.sp, color = Mx.Muted)
                    if (e.str("kind") == "photo") EvidencePhoto(e.str("file"))
                    if (e.str("text").isNotEmpty()) Text(e.str("text"), fontSize = 14.sp, color = Mx.Ink)
                }
            }
            if ("statement" in actions) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LineButton("Add a statement", { dialog = "statement" }, Modifier.weight(1f))
                    LineButton("Add a photo", { dialog = "photo" }, Modifier.weight(1f), enabled = !busy)
                }
            }

            // Timeline
            Text("What happened", fontWeight = FontWeight.Bold, color = Mx.Ink, modifier = Modifier.padding(top = 4.dp))
            d.optJSONArray("timeline")?.objects().orEmpty().forEach { t ->
                Text("${Format.dateTime(t.str("at"))}  ${who(t.str("by"), you)} ${EVENTS[t.str("kind")] ?: t.str("kind")}",
                    fontSize = 12.sp, color = Mx.Body)
            }
            Spacer(Modifier.navigationBarsPadding().height(16.dp))
        }
    }

    val d = loader.data
    when (dialog) {
        "offer" -> if (d != null) OfferDialog(d.str("amount"), d.str("you"), onDismiss = { dialog = null }) { refund, note ->
            dialog = null
            post("offers", JSONObject().put("buyer_refund", refund).put("note", note), "Offer sent")
        }
        "statement" -> TextDialog("Add a statement", "What happened, in your words", "Add", onDismiss = { dialog = null }) { text ->
            dialog = null
            post("statements", JSONObject().put("text", text), "Statement added")
        }
        "appeal" -> TextDialog("Appeal the decision", "Why the decision is wrong", "Send appeal", min = 5,
            note = "You can appeal once. A senior staff member who did not make this decision will decide, and that is final.",
            onDismiss = { dialog = null }) { text ->
            dialog = null
            post("appeal", JSONObject().put("reason", text), "Appeal sent")
        }
        "photo" -> AlertDialog(
            onDismissRequest = { dialog = null },
            title = { Text("Add a photo") },
            text = { Text("Show the item, packaging or receipt. Up to 5 photos each.") },
            confirmButton = {
                TextButton(onClick = {
                    dialog = null
                    val file = java.io.File(context.cacheDir, "dispute-camera.jpg")
                    cameraUri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                    camera.launch(cameraUri!!)
                }) { Text("Take a photo") }
            },
            dismissButton = {
                TextButton(onClick = { dialog = null; gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }) { Text("Choose from gallery") }
            },
        )
    }
}

/** Negotiate › Mediator › Appeal, with the current one highlighted and its deadline. */
@Composable
private fun StageTrack(d: JSONObject) {
    val stage = d.str("stage")
    val current = when (stage) { "negotiation" -> 0; "mediation" -> 1; "resolved" -> 3; else -> 2 }
    val labels = listOf("Agree", "Mediator", if (stage == "appeal") "Appeal" else "Final")
    Row(Modifier.fillMaxWidth().testTag("stage-track"), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        labels.forEachIndexed { i, label ->
            val done = i < current
            val now = i == current
            Column(Modifier.weight(1f)) {
                Box(Modifier.fillMaxWidth().height(5.dp).clip(RoundedCornerShape(3.dp))
                    .background(if (done) Mx.Green else if (now) Mx.Gold else Mx.Line))
                Text(label, fontSize = 12.sp, fontWeight = if (now) FontWeight.Bold else FontWeight.Medium,
                    color = if (now) Mx.Ink else Mx.Muted, modifier = Modifier.padding(top = 4.dp))
            }
        }
    }
}

private fun explain(d: JSONObject, you: String, otherName: String): String {
    val other = if (you == "buyer") "seller" else "buyer"
    return when (d.str("stage")) {
        "negotiation" -> "You and $otherName have until ${Format.dateTime(d.str("negotiate_until"))} to agree. Make an offer of how much the buyer " +
            "gets back; if the $other accepts, the Stars move at once. If you don't agree, a mediator decides."
        "mediation" -> "A mediator decides by ${Format.dateTime(d.str("mediator_due"))} (5 working days). Add statements and photos now. " +
            "You can still settle with an offer until then."
        "decided" -> "Accept the decision, or appeal once before ${Format.dateTime(d.str("appeal_until"))}."
        "appeal" -> "A senior staff member is deciding the appeal. Their decision is final."
        else -> "This dispute is closed."
    }
}

private fun offerStatus(status: String, mine: Boolean): String = when (status) {
    "open" -> if (mine) "waiting for an answer" else "waiting for you"
    "accepted" -> "accepted"
    "rejected" -> "rejected"
    "withdrawn" -> "withdrawn"
    "replaced" -> "replaced by a newer offer"
    else -> "closed by the decision"
}

private val EVENTS = mapOf(
    "opened" to "opened the dispute", "offer" to "made an offer", "offer_rejected" to "rejected an offer",
    "offer_withdrawn" to "withdrew an offer", "offer_accepted" to "accepted an offer", "escalated" to "asked for a mediator",
    "assigned" to "took the case", "statement" to "added a statement", "photo" to "added a photo", "decided" to "decided",
    "accepted" to "accepted the decision", "appealed" to "appealed", "resolved" to "closed the dispute",
)

private fun who(by: String, you: String): String = when (by) {
    you -> "You"
    "staff" -> "A mediator"
    "McXus" -> "McXus"
    else -> "The $by"
}

/** My disputes (Me › Disputes): newest first, with the stage. */
@Composable
fun DisputesListScreen(nav: NavHostController) {
    val app = LocalApp.current
    val loader = rememberLoader("disputes") { app.api.list("/v1/disputes").objects() }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("Disputes", onBack = { nav.back() })
        val items = loader.data
        when {
            items == null -> if (loader.error != null) Empty(loader.error!!) else Loading()
            items.isEmpty() -> Empty("No disputes. If something goes wrong with an order, open one from the order.")
            else -> Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items.forEach { d ->
                    Card(Modifier.clickable { nav.navigate("dispute/${d.str("order_id")}") }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(d.str("title"), fontWeight = FontWeight.Bold, color = Mx.Ink, modifier = Modifier.weight(1f))
                            Text(Format.kina(d.str("amount")), fontWeight = FontWeight.Bold, color = Mx.Navy)
                        }
                        Text(STAGES[d.str("stage")] ?: d.str("stage"), fontSize = 13.sp,
                            color = if (d.str("stage") == "resolved") Mx.Green else Mx.GoldInk, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

private val STAGES = mapOf(
    "negotiation" to "Agreeing with the other person", "mediation" to "With a mediator", "decided" to "Decided — accept or appeal",
    "appeal" to "Appeal being decided", "resolved" to "Closed",
)

/** amount - refund, exact to the cent. */
internal fun minus(amount: String, refund: String): String =
    runCatching { BigDecimal(amount).subtract(BigDecimal(refund)).setScale(2).toPlainString() }.getOrDefault(amount)

@Composable
private fun EvidencePhoto(path: String) {
    val app = LocalApp.current
    var bitmap by remember(path) { mutableStateOf<android.graphics.Bitmap?>(null) }
    LaunchedEffect(path) {
        // Dispute photos need the sign-in, so they are fetched with it (not through the public photo cache).
        bitmap = runCatching { app.api.getBytes(path).let { BitmapFactory.decodeByteArray(it, 0, it.size) } }.getOrNull()
    }
    Box(Modifier.fillMaxWidth().heightIn(min = 120.dp).padding(vertical = 6.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Slate),
        contentAlignment = Alignment.Center) {
        bitmap?.let { Image(it.asImageBitmap(), "Dispute photo", Modifier.fillMaxWidth(), contentScale = ContentScale.FillWidth) }
            ?: Text("Loading photo…", fontSize = 12.sp, color = Mx.Muted)
    }
}

@Composable
private fun OfferDialog(amount: String, you: String, onDismiss: () -> Unit, onSend: (String, String) -> Unit) {
    var refund by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    val value = refund.trim().toBigDecimalOrNull()
    val total = BigDecimal(amount)
    val valid = value != null && value.scale() <= 2 && value >= BigDecimal.ZERO && value <= total
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Make an offer") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(if (you == "buyer") "How much should you get back?" else "How much should the buyer get back?", fontSize = 14.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("All" to total, "Half" to total.divide(BigDecimal(2)).setScale(2, java.math.RoundingMode.HALF_UP), "None" to BigDecimal.ZERO).forEach { (label, v) ->
                        Text(label, Modifier.clip(RoundedCornerShape(10.dp)).background(Mx.Tint).clickable { refund = v.setScale(2).toPlainString() }
                            .padding(horizontal = 12.dp, vertical = 6.dp), fontWeight = FontWeight.SemiBold, color = Mx.Blue)
                    }
                }
                Field(refund, { refund = it.filter { c -> c.isDigit() || c == '.' }.take(10) }, "Buyer gets back (K)", keyboard = KeyboardType.Decimal, tag = "offer-amount")
                if (valid) Text("Buyer ${Format.kina(value!!.setScale(2).toPlainString())} · seller ${Format.kina(minus(amount, value.setScale(2).toPlainString()))}",
                    fontSize = 12.sp, color = Mx.Muted)
                else if (refund.isNotEmpty()) Text("Between K0 and ${Format.kina(amount)}", fontSize = 12.sp, color = Mx.Red)
                Field(note, { note = it.take(500) }, "Message (optional)", singleLine = false, minLines = 2)
            }
        },
        confirmButton = { TextButton(enabled = valid, onClick = { onSend(value!!.setScale(2).toPlainString(), note.trim()) }) { Text("Send offer") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun TextDialog(
    title: String, label: String, confirm: String, onDismiss: () -> Unit, min: Int = 1, note: String? = null, onSend: (String) -> Unit,
) {
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                note?.let { Text(it, fontSize = 13.sp, color = Mx.Body, textAlign = TextAlign.Start) }
                Field(text, { text = it.take(2000) }, label, singleLine = false, minLines = 4, tag = "dispute-text")
            }
        },
        confirmButton = { TextButton(enabled = text.trim().length >= min, onClick = { onSend(text.trim()) }) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
