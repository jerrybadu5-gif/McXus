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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableIntStateOf
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
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.RemoteImage
import pg.mcxus.app.ui.RoundIcon
import pg.mcxus.app.ui.SellerBadge
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Format
import java.time.Duration
import java.time.OffsetDateTime

/**
 * Discover: status of the people I chat with, then a feed of posts (public, my contacts', my channels') mixed with
 * new listings. "Following" shows only channel posts and people I chat with; "Nearby" is listings near me (later).
 */
@Composable
fun DiscoverTab(nav: NavHostController, openMarket: () -> Unit) {
    val app = LocalApp.current
    var feed by rememberSaveable { mutableIntStateOf(0) }
    var refresh by rememberSaveable { mutableIntStateOf(0) }
    var menu by remember { mutableStateOf(false) }
    val items = remember(feed, refresh) { mutableStateListOf<JSONObject>() }
    var next by remember(feed, refresh) { mutableStateOf<String?>("") }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun loadMore() {
        val cursor = next ?: return
        if (loading) return
        loading = true
        app.launch(onDone = { loading = false }, onError = { error = it }) {
            val q = StringBuilder("/v1/feed?limit=20")
            if (cursor.isNotEmpty()) q.append("&before=").append(java.net.URLEncoder.encode(cursor, "UTF-8"))
            if (feed == 1) q.append("&listings=false")
            val page = app.api.obj(q.toString())
            val got = page.optJSONArray("items")?.objects().orEmpty()
            items += if (feed == 1) got.filter { it.optJSONObject("post")?.let { p -> !p.isNull("channel") || p.str("visibility") == "contacts" } == true } else got
            next = if (page.isNull("next_before")) null else page.str("next_before")
            error = null
        }
    }
    androidx.compose.runtime.LaunchedEffect(feed, refresh) { loadMore() }

    LazyColumn(Modifier.fillMaxSize().testTag("discover"), contentPadding = PaddingValues(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Row(
                Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Discover", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f))
                RoundIcon(Ic.Group, "Channels", onClick = { nav.navigate(Routes.CHANNELS) })
                Box {
                    RoundIcon(Ic.Plus, "Post something", onClick = { menu = true })
                    androidx.compose.material3.DropdownMenu(menu, { menu = false }) {
                        androidx.compose.material3.DropdownMenuItem(text = { Text("Write a post") }, onClick = { menu = false; nav.navigate(Routes.newPost()) })
                        androidx.compose.material3.DropdownMenuItem(text = { Text("Add a status (24 h)") }, onClick = { menu = false; nav.navigate(Routes.STATUS_NEW) })
                        androidx.compose.material3.DropdownMenuItem(text = { Text("Sell something") }, onClick = { menu = false; nav.navigate(Routes.SELL) })
                    }
                }
            }
        }
        item { StatusStrip(nav, refresh) }
        item {
            Row(Modifier.padding(horizontal = 16.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Color(0xFFE3E9F0)).padding(4.dp)) {
                listOf("For you", "Following", "Nearby").forEachIndexed { i, label ->
                    Box(
                        Modifier.weight(1f).height(36.dp).clip(RoundedCornerShape(11.dp)).background(if (feed == i) Color.White else Color.Transparent)
                            .clickable { if (i == 2) app.say("Nearby arrives with location filters. Use Market › filters for now.") else feed = i }
                            .testTag("feed-$label"),
                        contentAlignment = Alignment.Center,
                    ) { Text(label, fontSize = 13.sp, fontWeight = if (feed == i) FontWeight.Bold else FontWeight.SemiBold, color = if (feed == i) Mx.Navy else Mx.Muted) }
                }
            }
        }
        item {
            Row(
                Modifier.padding(horizontal = 16.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Color.White)
                    .clickable { nav.navigate(Routes.newPost()) }.padding(12.dp).testTag("write-post"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Avatar(app.displayName.ifBlank { "Me" }, 36.dp, key = app.session.userId.orEmpty())
                Text("What's happening?", color = Mx.Muted, modifier = Modifier.weight(1f))
                Icon(Ic.Image, null, tint = Mx.Blue)
            }
        }
        items(items, key = { (it.str("type")) + (it.optJSONObject("post")?.str("id") ?: it.optJSONObject("listing")?.str("id")) }) { item ->
            when (item.str("type")) {
                "post" -> PostCard(item.getJSONObject("post"), nav, { changed -> if (changed == null) refresh++ })
                else -> ListingPost(item.getJSONObject("listing"), nav, openMarket)
            }
        }
        item {
            when {
                error != null && items.isEmpty() -> Empty(error!!)
                loading -> Loading()
                items.isEmpty() -> Empty(if (feed == 1) "Follow channels (top right) and chat with people to fill this feed." else "Nothing new yet. Write the first post!")
                next != null -> LineButton("Show more", { loadMore() }, Modifier.fillMaxWidth().padding(horizontal = 16.dp))
            }
        }
    }
}


@Composable
private fun ListingPost(item: JSONObject, nav: NavHostController, openMarket: () -> Unit) {
    val app = LocalApp.current
    val seller = item.getJSONObject("seller")
    val mine = seller.str("id") == app.session.userId
    Column(Modifier.fillMaxWidth().background(Color.White)) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Avatar(seller.str("name"), 42.dp, key = seller.str("id"))
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(seller.str("name"), fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false))
                    SellerBadge(seller.str("badge"))
                }
                Text(listOf(place(item), ago(item.str("created_at"))).filter { it.isNotEmpty() }.joinToString(" · "), fontSize = 12.sp, color = Mx.Muted)
            }
        }
        val text = item.str("description").ifEmpty { item.str("title") }
        Text(text, Modifier.padding(start = 16.dp, end = 16.dp, bottom = 10.dp), fontSize = 15.sp, lineHeight = 21.sp, maxLines = 4, overflow = TextOverflow.Ellipsis)
        Box(Modifier.fillMaxWidth().height(250.dp).clickable { nav.navigate(Routes.listing(item.str("id"))) }) {
            RemoteImage(item.optJSONArray("photos")?.objects()?.firstOrNull()?.str("url"), Modifier.fillMaxSize(), item.str("title"))
            Row(
                Modifier.align(Alignment.BottomStart).padding(12.dp).clip(RoundedCornerShape(12.dp)).background(Color.White).padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Ic.Market, null, tint = Mx.Navy, modifier = Modifier.size(16.dp))
                Text("  ${item.str("title").take(28)} · ${Format.kina(item.str("price"))}", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Mx.Navy)
            }
        }
        Row(Modifier.padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("From the market", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.padding(start = 10.dp))
            Icon(Ic.Market, "Open in Market", tint = Mx.Ink, modifier = Modifier.padding(10.dp).size(22.dp).clickable { openMarket() })
            Box(Modifier.weight(1f))
            if (!mine) {
                Text(
                    "Message",
                    Modifier.clip(RoundedCornerShape(18.dp)).background(Mx.Blue).clickable {
                        val engine = app.chat ?: return@clickable app.say("Encryption is still starting, try again in a second.", error = true)
                        app.launch {
                            val conv = engine.open(seller.str("id"), item.str("id"))
                            // The post goes with my first message, like replying to it (shown above the message box).
                            val thumb = item.optJSONArray("photos")?.objects()?.firstOrNull()?.str("thumb_url").orEmpty()
                            app.pendingCard[conv] = pg.mcxus.app.chat.Payload.listing(item.str("id"), item.str("title"), item.str("price"), thumb)
                            nav.navigate(Routes.chat(conv))
                        }
                    }.padding(horizontal = 14.dp, vertical = 9.dp),
                    color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp,
                )
            }
        }
    }
}
