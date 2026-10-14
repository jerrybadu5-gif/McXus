package pg.mcxus.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONArray
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.Pill
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format

private data class Choice(val id: Int, val name: String)

/** Create a listing, then add up to 5 photos. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SellScreen(nav: NavHostController) {
    val app = LocalApp.current
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var price by remember { mutableStateOf("") }
    var quantity by remember { mutableStateOf("1") }
    var category by remember { mutableStateOf<Choice?>(null) }
    var condition by remember { mutableStateOf("good") }
    var delivery by remember { mutableStateOf(setOf("meetup")) }
    var province by remember { mutableStateOf<Choice?>(null) }
    var district by remember { mutableStateOf<Choice?>(null) }
    var suburb by remember { mutableStateOf<Choice?>(null) }
    var busy by remember { mutableStateOf(false) }
    var created by remember { mutableStateOf<String?>(null) }

    val categories = rememberLoader(Unit) {
        app.api.list("/v1/categories").objects().flatMap { parent ->
            val kids = (parent.optJSONArray("children") ?: JSONArray()).objects()
            // Listings go in a specific (leaf) category, e.g. "Electronics › Solar & power".
            if (kids.isEmpty()) listOf(Choice(parent.getInt("id"), parent.str("name")))
            else kids.map { Choice(it.getInt("id"), parent.str("name") + " › " + it.str("name")) }
        }
    }
    val provinces = rememberLoader(Unit) { app.api.list("/v1/locations").objects().map { Choice(it.getInt("id"), it.str("name")) } }
    val districts = rememberLoader(province) {
        province?.let { p -> app.api.list("/v1/locations?parent_id=${p.id}").objects().map { Choice(it.getInt("id"), it.str("name")) } }.orEmpty()
    }
    val suburbs = rememberLoader(district) {
        district?.let { d -> app.api.list("/v1/locations?parent_id=${d.id}").objects().map { Choice(it.getInt("id"), it.str("name")) } }.orEmpty()
    }

    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header(if (created == null) "Sell something" else "Add photos", onBack = { nav.back() })
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val listingId = created
            if (listingId != null) {
                Note("Listing created. Clear photos sell faster — add up to 5. Location data is removed from photos automatically.")
                pg.mcxus.app.ui.PhotoButtons(listingId) { }
                BigButton("View my listing", onClick = { nav.navigate(Routes.listing(listingId)) { popUpTo(Routes.HOME) } })
                return@Column
            }
            Field(title, { title = it }, "Title, e.g. Solar lamp with phone charger")
            Field(price, { price = it }, "Price in Kina (1 Star = K1)", keyboard = KeyboardType.Decimal)
            Field(quantity, { quantity = it.filter(Char::isDigit).take(5) }, "How many?", keyboard = KeyboardType.Number)
            Picker("Category", category, categories.data.orEmpty()) { category = it }
            Text("Condition", fontWeight = FontWeight.Bold)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("new", "like_new", "good", "fair", "not_applicable").forEach {
                    Pill(if (it == "not_applicable") "Not an item" else Format.condition(it), condition == it, { condition = it })
                }
            }
            Text("Delivery", fontWeight = FontWeight.Bold)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("meetup", "pickup", "seller_delivers", "courier").forEach { d ->
                    Pill(Format.delivery(d), d in delivery, { delivery = if (d in delivery && delivery.size > 1) delivery - d else delivery + d })
                }
            }
            Picker("Province", province, provinces.data.orEmpty()) { province = it; district = null; suburb = null }
            if (districts.data.orEmpty().isNotEmpty()) Picker("District (optional)", district, districts.data.orEmpty()) { district = it; suburb = null }
            if (suburbs.data.orEmpty().isNotEmpty()) Picker("Suburb (optional)", suburb, suburbs.data.orEmpty()) { suburb = it }
            Field(description, { description = it }, "Description: size, colour, where to meet…", singleLine = false, minLines = 3)
            Note("Buyers pay into escrow. You receive the Stars when the buyer gives you their handover PIN. A 3% fee applies to completed sales.")
            Box(Modifier.height(4.dp))
        }
        if (created == null) {
            BigButton(
                "Post listing", busy = busy,
                modifier = Modifier.navigationBarsPadding().padding(16.dp),
                onClick = {
                    val amount = Format.amount(price)
                    when {
                        title.trim().length < 3 -> app.say("Please write a title (3 letters or more)")
                        amount == null -> app.say("Please enter a price like 120 or 12.50")
                        category == null -> app.say("Please choose a category")
                        province == null -> app.say("Please choose a province")
                        else -> {
                            busy = true
                            app.launch(onDone = { busy = false }) {
                                val body = JSONObject()
                                    .put("title", title.trim()).put("description", description.trim())
                                    .put("category_id", category!!.id).put("price", amount)
                                    .put("quantity", quantity.toIntOrNull() ?: 1).put("condition", condition)
                                    .put("delivery_options", JSONArray(delivery.toList()))
                                    .put("province_id", province!!.id)
                                    .put("district_id", district?.id ?: JSONObject.NULL)
                                    .put("suburb_id", suburb?.id ?: JSONObject.NULL)
                                created = app.api.post("/v1/listings", body).getString("id")
                            }
                        }
                    }
                },
            )
        }
    }
}

@Composable
private fun Picker(label: String, selected: Choice?, options: List<Choice>, onPick: (Choice) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        Row(
            Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(14.dp)).background(Color.White)
                .border(1.dp, Mx.Field, RoundedCornerShape(14.dp)).clickable { open = true }.padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                if (selected != null) Text(label, fontSize = 11.sp, color = Mx.Muted)
                Text(selected?.name ?: label, color = if (selected == null) Mx.Muted else Mx.Ink, fontSize = 15.sp)
            }
            Icon(Ic.Down, null, modifier = Modifier.size(18.dp))
        }
        DropdownMenu(open, onDismissRequest = { open = false }) {
            options.forEach { DropdownMenuItem(text = { Text(it.name) }, onClick = { onPick(it); open = false }) }
        }
    }
}
