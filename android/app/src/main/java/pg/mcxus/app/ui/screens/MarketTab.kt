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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.Pill
import pg.mcxus.app.ui.RemoteImage
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Jakarta
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format
import java.net.URLEncoder

fun place(item: JSONObject): String =
    listOf(item.str("suburb"), item.str("district"), item.str("province")).filter { it.isNotEmpty() }.take(2).joinToString(", ")

@Composable
fun MarketTab(nav: NavHostController) {
    val app = LocalApp.current
    var typed by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf("") }
    var provinceId by rememberSaveable { mutableStateOf<Int?>(null) }
    var provinceName by rememberSaveable { mutableStateOf("All PNG") }
    var picking by rememberSaveable { mutableStateOf(false) }

    val categories = rememberLoader(Unit) { app.api.list("/v1/categories").objects() }
    val provinces = rememberLoader(Unit) { app.api.list("/v1/locations").objects() }
    val listings = rememberLoader(query, category, provinceId) {
        val params = buildList {
            add("limit=40")
            if (query.isNotBlank()) add("q=" + URLEncoder.encode(query.trim(), "UTF-8"))
            if (category.isNotEmpty()) add("category=$category")
            provinceId?.let { add("province_id=$it") }
        }.joinToString("&")
        app.api.list("/v1/listings?$params").objects()
    }

    Box(Modifier.fillMaxSize()) {
        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 96.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxSize().testTag("market-grid"),
        ) {
            item(span = { GridItemSpan(2) }) {
                Column(Modifier.statusBarsPadding().padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Market", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                        Box {
                            Row(
                                Modifier.height(36.dp).clip(RoundedCornerShape(18.dp)).background(Color.White)
                                    .border(1.dp, Mx.ChipLine, RoundedCornerShape(18.dp)).clickable { picking = true }
                                    .padding(horizontal = 12.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(Ic.Pin, null, tint = Mx.Blue, modifier = Modifier.size(16.dp))
                                Text(" $provinceName ", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
                                Icon(Ic.Down, null, modifier = Modifier.size(14.dp))
                            }
                            DropdownMenu(picking, onDismissRequest = { picking = false }) {
                                DropdownMenuItem(text = { Text("All PNG") }, onClick = { provinceId = null; provinceName = "All PNG"; picking = false })
                                provinces.data.orEmpty().forEach { p ->
                                    DropdownMenuItem(text = { Text(p.str("name")) }, onClick = {
                                        provinceId = p.getInt("id"); provinceName = p.str("name"); picking = false
                                    })
                                }
                            }
                        }
                    }
                    Row(
                        Modifier.fillMaxWidth().height(46.dp).clip(RoundedCornerShape(14.dp)).background(Color.White)
                            .border(1.dp, Mx.Field, RoundedCornerShape(14.dp)).padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(Ic.Search, null, tint = Mx.Muted, modifier = Modifier.size(20.dp))
                        BasicTextField(
                            typed, { typed = it },
                            singleLine = true,
                            textStyle = TextStyle(fontFamily = Jakarta, fontSize = 15.sp, color = Mx.Ink),
                            cursorBrush = SolidColor(Mx.Blue),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                            keyboardActions = KeyboardActions(onSearch = { query = typed }),
                            modifier = Modifier.weight(1f).padding(start = 8.dp).testTag("market-search"),
                            decorationBox = { inner ->
                                if (typed.isEmpty()) Text("Search solar, bilum, kaukau…", color = Mx.Muted, fontSize = 15.sp)
                                inner()
                            },
                        )
                    }
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        item { Pill("All", category.isEmpty(), { category = "" }) }
                        items(categories.data.orEmpty(), key = { it.str("slug") }) { c ->
                            Pill(c.str("name"), category == c.str("slug"), { category = c.str("slug") })
                        }
                    }
                    Note("Every purchase is held in escrow until you receive it.", dark = true)
                }
            }
            val items = listings.data
            when {
                items == null && listings.error != null -> item(span = { GridItemSpan(2) }) { Empty(listings.error!!) }
                items == null -> item(span = { GridItemSpan(2) }) { Loading() }
                items.isEmpty() -> item(span = { GridItemSpan(2) }) { Empty("No listings found. Be the first to sell here!") }
                else -> items(items, key = { it.str("id") }) { ListingTile(it) { nav.navigate(Routes.listing(it.str("id"))) } }
            }
        }
        ExtendedFloatingActionButton(
            onClick = { nav.navigate(Routes.SELL) },
            containerColor = Mx.Gold, contentColor = Mx.Navy, shape = RoundedCornerShape(26.dp),
            modifier = Modifier.align(Alignment.BottomEnd).padding(18.dp).testTag("sell"),
            icon = { Icon(Ic.Plus, null, modifier = Modifier.size(20.dp)) },
            text = { Text("Sell", fontWeight = FontWeight.ExtraBold, fontSize = 15.sp) },
        )
    }
}

@Composable
fun ListingTile(item: JSONObject, onClick: () -> Unit) {
    Column(Modifier.clip(RoundedCornerShape(16.dp)).background(Color.White).clickable(onClick = onClick)) {
        Box {
            RemoteImage(item.optJSONArray("photos")?.objects()?.firstOrNull()?.str("thumb_url"), Modifier.fillMaxWidth().height(128.dp), item.str("title"))
            if (item.optInt("quantity_available", 1) == 0) {
                Text("Sold out", Modifier.padding(8.dp).clip(RoundedCornerShape(8.dp)).background(Mx.Ink).padding(horizontal = 8.dp, vertical = 3.dp),
                    color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
            }
        }
        Column(Modifier.padding(start = 10.dp, end = 10.dp, top = 8.dp, bottom = 10.dp)) {
            Text(Format.kina(item.str("price")), color = Mx.Blue, fontWeight = FontWeight.ExtraBold, fontSize = 15.sp)
            Text(item.str("title"), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val seller = item.optJSONObject("seller")
            Text(
                listOfNotNull(place(item).ifEmpty { null }, seller?.str("badge")?.takeIf { it.isNotEmpty() }?.let(Format::badge)).joinToString(" · "),
                fontSize = 11.sp, color = Mx.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
