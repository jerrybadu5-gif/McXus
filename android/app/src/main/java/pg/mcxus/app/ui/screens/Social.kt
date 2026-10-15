package pg.mcxus.app.ui.screens

import android.graphics.BitmapFactory
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Card
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.RemoteImage
import pg.mcxus.app.ui.objects
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx
import pg.mcxus.app.util.Images
import java.net.URLEncoder
import java.time.Duration
import java.time.OffsetDateTime

// ---------------------------------------------------------------- status

private val STATUS_COLORS = listOf("#0B2545", "#134074", "#1B7F5A", "#B9771A", "#B3261E", "#5B3A8C")

private fun color(hex: String): Color = runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(Mx.Navy)

fun ago(iso: String): String = try {
    val d = Duration.between(OffsetDateTime.parse(iso), OffsetDateTime.now())
    when {
        d.toMinutes() < 1 -> "now"
        d.toMinutes() < 60 -> "${d.toMinutes()} min"
        d.toHours() < 24 -> "${d.toHours()} h"
        else -> "${d.toDays()} d"
    }
} catch (e: Exception) {
    ""
}

/** "My status" plus the people I chat with who have a status now (gold ring = not seen yet). */
@Composable
fun StatusStrip(nav: NavHostController, refresh: Int) {
    val app = LocalApp.current
    val board = rememberLoader("status-board", refresh) { app.api.obj("/v1/status") }
    val b = board.data
    LazyRow(Modifier.testTag("status-strip"), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        item {
            val mine = b?.optJSONArray("mine")?.length() ?: 0
            StatusBubble(app.displayName.ifBlank { "Me" }, app.session.userId.orEmpty(), if (mine > 0) Mx.Blue else null, "My status",
                plus = mine == 0) { if (mine > 0) nav.navigate(Routes.status("me")) else nav.navigate(Routes.STATUS_NEW) }
        }
        items(b?.optJSONArray("contacts")?.objects().orEmpty(), key = { it.getJSONObject("user").str("id") }) { g ->
            val user = g.getJSONObject("user")
            StatusBubble(user.str("name"), user.str("id"), if (g.optBoolean("all_seen")) Mx.Grey else Mx.Gold, user.str("name")) {
                nav.navigate(Routes.status(user.str("id")))
            }
        }
    }
}

@Composable
private fun StatusBubble(name: String, key: String, ring: Color?, label: String, plus: Boolean = false, onClick: () -> Unit) {
    Column(Modifier.width(64.dp).clickable(onClick = onClick), horizontalAlignment = Alignment.CenterHorizontally) {
        Box {
            Box(Modifier.size(60.dp).border(2.5.dp, ring ?: Color.Transparent, CircleShape).padding(4.dp)) { Avatar(name, 52.dp, key = key) }
            if (plus) {
                Box(Modifier.align(Alignment.BottomEnd).size(22.dp).clip(CircleShape).background(Mx.Blue).border(2.dp, Color.White, CircleShape),
                    contentAlignment = Alignment.Center) { Icon(Ic.Plus, null, tint = Color.White, modifier = Modifier.size(14.dp)) }
            }
        }
        Text(label, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Mx.Body, modifier = Modifier.padding(top = 4.dp))
    }
}

/** Full-screen status, one after another (5 s each, tap right/left to move). "me" shows my own with who saw them. */
@Composable
fun StatusViewerScreen(nav: NavHostController, who: String) {
    val app = LocalApp.current
    val board = rememberLoader("status-view", who) { app.api.obj("/v1/status") }
    val b = board.data ?: return Box(Modifier.fillMaxSize().background(Color.Black)) { if (board.error != null) Empty(board.error!!) else Loading() }
    val mine = who == "me"
    val group = if (mine) null else b.optJSONArray("contacts")?.objects()?.firstOrNull { it.getJSONObject("user").str("id") == who }
    val items = if (mine) b.optJSONArray("mine")?.objects().orEmpty() else group?.optJSONArray("items")?.objects().orEmpty()
    val name = if (mine) "My status" else group?.getJSONObject("user")?.str("name").orEmpty()
    if (items.isEmpty()) { LaunchedEffect(Unit) { nav.back() }; return }
    var index by remember { mutableIntStateOf(items.indexOfFirst { !it.optBoolean("seen") }.coerceAtLeast(0)) }
    var progress by remember { mutableFloatStateOf(0f) }
    var paused by remember { mutableStateOf(false) }
    var showViewers by remember { mutableStateOf(false) }
    val item = items[index.coerceIn(0, items.lastIndex)]

    LaunchedEffect(item.str("id")) {
        if (!mine) runCatching { app.api.post("/v1/status/${item.str("id")}/seen") }
        progress = 0f
        while (progress < 1f) {
            delay(50)
            if (!paused) progress += 50f / 5000f
        }
        if (index < items.lastIndex) index++ else nav.back()
    }

    Box(Modifier.fillMaxSize().background(if (item.str("kind") == "text") color(item.str("color")) else Color.Black).testTag("status-viewer")
        .pointerInput(index) {
            detectTapGestures(
                onPress = { paused = true; tryAwaitRelease(); paused = false },
                onTap = { pos -> if (pos.x < size.width / 3) { if (index > 0) index-- } else { if (index < items.lastIndex) index++ else nav.back() } },
            )
        }) {
        if (item.str("kind") == "photo") {
            AuthImage(item.str("photo"), Modifier.fillMaxSize().align(Alignment.Center))
            if (item.str("text").isNotEmpty()) Text(item.str("text"), Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .background(Color(0x99000000)).navigationBarsPadding().padding(16.dp), color = Color.White, fontSize = 16.sp, textAlign = TextAlign.Center)
        } else {
            Text(item.str("text"), Modifier.align(Alignment.Center).padding(28.dp), color = Color.White, fontSize = 26.sp,
                fontWeight = FontWeight.Bold, textAlign = TextAlign.Center, lineHeight = 34.sp)
        }
        Column(Modifier.fillMaxWidth().statusBarsPadding().padding(10.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                items.forEachIndexed { i, _ ->
                    LinearProgressIndicator(progress = { if (i < index) 1f else if (i == index) progress else 0f },
                        modifier = Modifier.weight(1f).height(3.dp).clip(RoundedCornerShape(2.dp)), color = Color.White, trackColor = Color(0x55FFFFFF))
                }
            }
            Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { nav.back() }) { Icon(Ic.Back, "Close", tint = Color.White) }
                Column(Modifier.weight(1f)) {
                    Text(name, color = Color.White, fontWeight = FontWeight.Bold)
                    Text(ago(item.str("created_at")), color = Color(0xCCFFFFFF), fontSize = 12.sp)
                }
            }
        }
        if (mine) {
            Row(Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("👁 Seen by ${item.optInt("views")}", Modifier.clip(RoundedCornerShape(18.dp)).background(Color(0x66000000))
                    .clickable { paused = true; showViewers = true }.padding(horizontal = 14.dp, vertical = 8.dp).testTag("seen-by"), color = Color.White)
                Text("Delete", Modifier.clip(RoundedCornerShape(18.dp)).background(Color(0x66000000)).clickable {
                    app.launch { app.api.delete("/v1/status/${item.str("id")}"); app.say("Status deleted"); nav.back() }
                }.padding(horizontal = 14.dp, vertical = 8.dp), color = Color.White)
                Text("+ Add", Modifier.clip(RoundedCornerShape(18.dp)).background(Mx.Gold).clickable { nav.navigate(Routes.STATUS_NEW) }
                    .padding(horizontal = 14.dp, vertical = 8.dp), color = Mx.Ink, fontWeight = FontWeight.Bold)
            }
        }
    }
    if (showViewers) {
        val viewers = rememberLoader("viewers", item.str("id")) { app.api.list("/v1/status/${item.str("id")}/viewers").objects() }
        AlertDialog(onDismissRequest = { showViewers = false; paused = false }, confirmButton = { TextButton(onClick = { showViewers = false; paused = false }) { Text("Close") } },
            title = { Text("Seen by") }, text = {
                Column {
                    val v = viewers.data
                    if (v == null) Loading() else if (v.isEmpty()) Text("Nobody yet.") else v.forEach {
                        Text("${it.getJSONObject("user").str("name")} · ${ago(it.str("seen_at"))}", Modifier.padding(vertical = 4.dp))
                    }
                }
            })
    }
}

/** A photo from the API that needs the sign-in (status photos). */
@Composable
fun AuthImage(path: String, modifier: Modifier = Modifier) {
    val app = LocalApp.current
    var bitmap by remember(path) { mutableStateOf<android.graphics.Bitmap?>(null) }
    LaunchedEffect(path) { bitmap = runCatching { app.api.getBytes(path).let { BitmapFactory.decodeByteArray(it, 0, it.size) } }.getOrNull() }
    Box(modifier, contentAlignment = Alignment.Center) {
        bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Fit) } ?: Loading()
    }
}

/** New status: words on a colour, or a photo with a caption. Seen by the people you chat with for 24 hours. */
@Composable
fun StatusComposeScreen(nav: NavHostController) {
    val app = LocalApp.current
    val context = LocalContext.current
    var text by remember { mutableStateOf("") }
    var bg by remember { mutableStateOf(STATUS_COLORS[0]) }
    var busy by remember { mutableStateOf(false) }
    var choosingHidden by remember { mutableStateOf(false) }
    var cameraUri by remember { mutableStateOf<android.net.Uri?>(null) }

    fun sendPhoto(uri: android.net.Uri) {
        busy = true
        app.launch(onDone = { busy = false }) {
            val jpeg = withContext(Dispatchers.Default) { Images.prepareUpload(context.contentResolver, uri, maxPx = 1600, quality = 80) }
            app.api.upload("/v1/status/photo?caption=" + URLEncoder.encode(text.trim(), "UTF-8"), jpeg)
            app.say("Status shared for 24 hours")
            nav.back()
        }
    }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { it?.let(::sendPhoto) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) cameraUri?.let(::sendPhoto) }

    Column(Modifier.fillMaxSize().background(color(bg)).statusBarsPadding().navigationBarsPadding().imePadding()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { nav.back() }) { Icon(Ic.Back, "Back", tint = Color.White) }
            Text("New status", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.weight(1f))
            TextButton(onClick = { choosingHidden = true }) { Text("Who sees it", color = Mx.Gold) }
        }
        androidx.compose.foundation.text.BasicTextField(
            value = text, onValueChange = { text = it.take(700) },
            textStyle = androidx.compose.ui.text.TextStyle(color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.White),
            modifier = Modifier.weight(1f).fillMaxWidth().padding(28.dp).testTag("status-text"),
            decorationBox = { inner ->
                Box(contentAlignment = Alignment.Center) {
                    if (text.isEmpty()) Text("Type a status", color = Color(0x99FFFFFF), fontSize = 26.sp, fontWeight = FontWeight.Bold)
                    inner()
                }
            },
        )
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            STATUS_COLORS.forEach { c ->
                Box(Modifier.size(30.dp).clip(CircleShape).background(color(c)).border(if (c == bg) 3.dp else 1.dp, Color.White, CircleShape).clickable { bg = c })
            }
        }
        Text("People you chat with see it for 24 hours. Statuses are not end-to-end encrypted like chats.",
            color = Color(0xCCFFFFFF), fontSize = 12.sp, modifier = Modifier.padding(16.dp))
        Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LineButton("Photo", { gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, Modifier.weight(1f), color = Color.White, enabled = !busy)
            LineButton("Camera", {
                val file = java.io.File(context.cacheDir, "status-camera.jpg")
                cameraUri = androidx.core.content.FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                camera.launch(cameraUri!!)
            }, Modifier.weight(1f), color = Color.White, enabled = !busy)
            BigButton("Share", busy = busy, enabled = text.isNotBlank(), modifier = Modifier.weight(1f).testTag("share-status"), color = Mx.Gold, textColor = Mx.Ink, onClick = {
                busy = true
                app.launch(onDone = { busy = false }) {
                    app.api.post("/v1/status", JSONObject().put("text", text.trim()).put("color", bg))
                    app.say("Status shared for 24 hours")
                    nav.back()
                }
            })
        }
    }
    if (choosingHidden) HiddenPicker { choosingHidden = false }
}

/** Choose people (from my chats) who should not see my status. */
@Composable
private fun HiddenPicker(onDone: () -> Unit) {
    val app = LocalApp.current
    val chats = app.chat?.conversations?.collectAsState()?.value.orEmpty()
    val people = chats.filter { !it.isGroup && it.peer != null }.map { it.peer!! }.distinctBy { it.id }
    val hidden = remember { mutableStateListOf<String>() }
    LaunchedEffect(Unit) {
        runCatching { app.api.get("/v1/status/hidden") }.getOrNull()?.let { raw ->
            val a = JSONArray(raw); hidden.clear(); (0 until a.length()).forEach { hidden += a.getString(it) }
        }
    }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Who sees my status") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("Everyone you chat with, except the people you tick.", fontSize = 13.sp, color = Mx.Muted)
                if (people.isEmpty()) Text("You have no chats yet.", Modifier.padding(top = 8.dp))
                people.forEach { p ->
                    Row(Modifier.fillMaxWidth().clickable { if (p.id in hidden) hidden.remove(p.id) else hidden += p.id }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(p.id in hidden, { if (p.id in hidden) hidden.remove(p.id) else hidden += p.id })
                        Text("Hide from ${p.name}")
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                app.launch { app.api.putRaw("/v1/status/hidden", JSONObject().put("user_ids", JSONArray(hidden.toList()))); app.say("Saved") }
                onDone()
            }) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Cancel") } },
    )
}

// ---------------------------------------------------------------- posts

/** A post on Discover or in a channel: author (or channel), text, photos, likes, comments, ⋮ report/delete. */
@Composable
fun PostCard(post: JSONObject, nav: NavHostController, onChanged: (JSONObject?) -> Unit, open: Boolean = true) {
    val app = LocalApp.current
    var p by remember(post.str("id"), post.optInt("likes"), post.optInt("comments")) { mutableStateOf(post) }
    var menu by remember { mutableStateOf(false) }
    var reporting by remember { mutableStateOf(false) }
    val channel = p.optJSONObject("channel")
    Column(Modifier.fillMaxWidth().background(Color.White).testTag("post-${p.str("id")}")) {
        Row(Modifier.padding(start = 16.dp, end = 4.dp, top = 12.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val author = p.getJSONObject("author")
            Avatar(channel?.str("name") ?: author.str("name"), 42.dp, key = channel?.str("id") ?: author.str("id"))
            Column(Modifier.weight(1f).clickable(enabled = channel != null) { channel?.let { nav.navigate(Routes.channel(it.str("id"))) } }) {
                Text(channel?.str("name") ?: author.str("name"), fontWeight = FontWeight.Bold, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val extra = listOfNotNull(
                    channel?.let { "@${it.str("handle")}" },
                    if (p.str("visibility") == "contacts") "people you chat with" else null,
                    ago(p.str("created_at")),
                ).joinToString(" · ")
                Text(extra, fontSize = 12.sp, color = Mx.Muted)
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Ic.More, "More", tint = Mx.Muted) }
                DropdownMenu(menu, { menu = false }) {
                    if (p.optBoolean("mine")) DropdownMenuItem(text = { Text("Delete post") }, onClick = {
                        menu = false
                        app.launch { app.api.delete("/v1/posts/${p.str("id")}"); app.say("Post deleted"); onChanged(null) }
                    }) else DropdownMenuItem(text = { Text("Report post") }, onClick = { menu = false; reporting = true })
                }
            }
        }
        if (p.str("status") != "visible") {
            Text(when (p.str("status")) { "under_review" -> "Hidden while a moderator checks reports"; "removed" -> "Removed by a moderator"; else -> "Deleted" },
                Modifier.padding(horizontal = 16.dp).clip(RoundedCornerShape(8.dp)).background(Mx.GoldSoft).padding(horizontal = 8.dp, vertical = 4.dp),
                fontSize = 12.sp, color = Mx.GoldInk)
        }
        if (p.str("text").isNotEmpty()) {
            Text(p.str("text"), Modifier.padding(horizontal = 16.dp, vertical = 4.dp).clickable(enabled = open) { nav.navigate(Routes.post(p.str("id"))) },
                fontSize = 15.sp, lineHeight = 21.sp, maxLines = if (open) 6 else Int.MAX_VALUE, overflow = TextOverflow.Ellipsis)
        }
        val photos = p.optJSONArray("photos")?.objects().orEmpty()
        if (photos.size == 1) {
            val ph = photos[0]
            RemoteImage(ph.str("url"), Modifier.fillMaxWidth().padding(top = 6.dp)
                .aspectRatio((ph.optDouble("width", 4.0) / ph.optDouble("height", 3.0)).toFloat().coerceIn(0.75f, 1.8f)))
        } else if (photos.isNotEmpty()) {
            Row(Modifier.fillMaxWidth().padding(top = 6.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                photos.forEach { ph ->
                    RemoteImage(ph.str("url"), Modifier.height(200.dp)
                        .aspectRatio((ph.optDouble("width", 4.0) / ph.optDouble("height", 3.0)).toFloat().coerceIn(0.6f, 1.8f)))
                }
            }
        }
        Row(Modifier.padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            val liked = p.optBoolean("liked")
            Row(Modifier.clip(RoundedCornerShape(18.dp)).clickable {
                app.launch {
                    val updated = if (liked) JSONObject(app.api.delete("/v1/posts/${p.str("id")}/like")) else app.api.post("/v1/posts/${p.str("id")}/like")
                    p = updated
                }
            }.padding(10.dp).testTag("like"), verticalAlignment = Alignment.CenterVertically) {
                Text(if (liked) "♥" else "♡", fontSize = 20.sp, color = if (liked) Mx.Red else Mx.Ink)
                Text("  ${p.optInt("likes")}", fontWeight = FontWeight.SemiBold)
            }
            Row(Modifier.clip(RoundedCornerShape(18.dp)).clickable(enabled = open) { nav.navigate(Routes.post(p.str("id"))) }.padding(10.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Icon(Ic.Chat, "Comments", tint = Mx.Ink, modifier = Modifier.size(20.dp))
                Text("  ${p.optInt("comments")}", fontWeight = FontWeight.SemiBold)
            }
        }
    }
    if (reporting) ReportDialog("post", p.str("id")) { reporting = false }
}

@Composable
fun ReportDialog(type: String, id: String, onDone: () -> Unit) {
    val app = LocalApp.current
    val reasons = listOf("scam" to "Scam or fraud", "offensive" to "Offensive or abusive", "prohibited" to "Banned item or illegal", "other" to "Something else")
    var reason by remember { mutableStateOf("scam") }
    var note by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Report this $type") },
        text = {
            Column {
                reasons.forEach { (key, label) ->
                    Row(Modifier.fillMaxWidth().clickable { reason = key }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        androidx.compose.material3.RadioButton(reason == key, { reason = key })
                        Text(label)
                    }
                }
                Field(note, { note = it.take(500) }, "What's wrong (optional)", singleLine = false, minLines = 2)
                Text("Three reports hide it until a McXus moderator decides.", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.padding(top = 6.dp))
            }
        },
        confirmButton = {
            TextButton(onClick = {
                app.launch {
                    app.api.post("/v1/reports", JSONObject().put("target_type", type).put("target_id", id).put("reason", reason).put("note", note))
                    app.say("Thanks. A moderator will look at it.")
                }
                onDone()
            }) { Text("Report") }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Cancel") } },
    )
}

/** One post with its comments; write a comment; report or delete comments. */
@Composable
fun PostScreen(nav: NavHostController, postId: String) {
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val post = rememberLoader(postId, refresh) { app.api.obj("/v1/posts/$postId") }
    val comments = rememberLoader("comments", postId, refresh) { app.api.list("/v1/posts/$postId/comments").objects() }
    var draft by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var reportingComment by remember { mutableStateOf<String?>(null) }
    Column(Modifier.fillMaxSize().background(Mx.Bg).imePadding()) {
        Header("Post", onBack = { nav.back() })
        LazyColumn(Modifier.weight(1f)) {
            item {
                val p = post.data
                if (p == null) { if (post.error != null) Empty(post.error!!) else Loading() } else PostCard(p, nav, { if (it == null) nav.back() }, open = false)
            }
            item { Text("Comments", fontWeight = FontWeight.Bold, modifier = Modifier.padding(16.dp)) }
            val list = comments.data.orEmpty()
            if (comments.data != null && list.isEmpty()) item { Text("No comments yet. Be the first.", color = Mx.Muted, modifier = Modifier.padding(horizontal = 16.dp)) }
            items(list, key = { it.str("id") }) { c ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    val u = c.getJSONObject("user")
                    Avatar(u.str("name"), 34.dp, key = u.str("id"))
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(Color.White).padding(10.dp)) {
                        Text("${u.str("name")} · ${ago(c.str("created_at"))}", fontSize = 12.sp, color = Mx.Muted)
                        Text(c.str("text"), fontSize = 14.sp)
                        if (c.str("status") == "under_review") Text("Hidden while a moderator checks reports", fontSize = 11.sp, color = Mx.GoldInk)
                        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.padding(top = 4.dp)) {
                            if (c.optBoolean("can_delete")) Text("Delete", fontSize = 12.sp, color = Mx.Red, modifier = Modifier.clickable {
                                app.launch { app.api.delete("/v1/comments/${c.str("id")}"); refresh++ }
                            })
                            if (!c.optBoolean("mine")) Text("Report", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.clickable { reportingComment = c.str("id") })
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().background(Color.White).navigationBarsPadding().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Field(draft, { draft = it.take(500) }, "Write a comment", Modifier.weight(1f), tag = "comment-text")
            Spacer(Modifier.width(8.dp))
            BigButton("Send", busy = busy, enabled = draft.isNotBlank(), modifier = Modifier.width(96.dp).testTag("send-comment"), onClick = {
                busy = true
                app.launch(onDone = { busy = false }) {
                    comments.data = app.api.multipartFree("/v1/posts/$postId/comments", JSONObject().put("text", draft.trim()))
                    draft = ""
                    refresh++
                }
            })
        }
    }
    reportingComment?.let { ReportDialog("comment", it) { reportingComment = null } }
}

/** Posting returns the full list of comments; keep that on the screen. */
private suspend fun pg.mcxus.app.net.Api.multipartFree(path: String, body: JSONObject): List<JSONObject> =
    JSONArray(postRaw(path, body)).objects()

/** New post: text and up to 4 photos, for everyone or only the people you chat with; or into a channel I run. */
@Composable
fun ComposePostScreen(nav: NavHostController, channelId: String?) {
    val app = LocalApp.current
    val context = LocalContext.current
    var text by remember { mutableStateOf("") }
    var everyone by remember { mutableStateOf(true) }
    val photos = remember { mutableStateListOf<ByteArray>() }
    var busy by remember { mutableStateOf(false) }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(4)) { uris ->
        app.launch {
            uris.take(4 - photos.size).forEach { uri ->
                photos += withContext(Dispatchers.Default) { Images.prepareUpload(context.contentResolver, uri, maxPx = 1600, quality = 80) }
            }
        }
    }
    Column(Modifier.fillMaxSize().background(Mx.Bg).imePadding()) {
        Header(if (channelId != null) "Post in channel" else "New post", onBack = { nav.back() })
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Field(text, { text = it.take(2000) }, "What's happening?", singleLine = false, minLines = 5, tag = "post-text")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.horizontalScroll(rememberScrollState())) {
                photos.forEachIndexed { i, jpeg ->
                    val bmp = remember(jpeg) { BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size).asImageBitmap() }
                    Box {
                        Image(bmp, null, Modifier.size(92.dp).clip(RoundedCornerShape(12.dp)), contentScale = ContentScale.Crop)
                        Text("✕", Modifier.align(Alignment.TopEnd).padding(4.dp).clip(CircleShape).background(Color(0x99000000))
                            .clickable { photos.removeAt(i) }.padding(horizontal = 6.dp), color = Color.White)
                    }
                }
                if (photos.size < 4) Box(Modifier.size(92.dp).clip(RoundedCornerShape(12.dp)).background(Mx.Tint)
                    .clickable { gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
                    contentAlignment = Alignment.Center) { Icon(Ic.Image, "Add photos", tint = Mx.Blue) }
            }
            if (channelId == null) {
                Text("Who sees it", fontWeight = FontWeight.Bold)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(true to "Everyone", false to "People I chat with").forEach { (value, label) ->
                        Text(label, Modifier.clip(RoundedCornerShape(18.dp)).background(if (everyone == value) Mx.Navy else Color.White)
                            .clickable { everyone = value }.padding(horizontal = 14.dp, vertical = 8.dp),
                            color = if (everyone == value) Color.White else Mx.Body, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
            Note("Posts are not end-to-end encrypted like chats. Photos lose their location data. Never post PINs or payment details.")
        }
        BigButton("Post", busy = busy, enabled = text.isNotBlank() || photos.isNotEmpty(),
            modifier = Modifier.navigationBarsPadding().padding(16.dp).testTag("publish-post"), onClick = {
                busy = true
                app.launch(onDone = { busy = false }) {
                    val fields = mutableMapOf("text" to text.trim(), "visibility" to if (everyone) "everyone" else "contacts")
                    channelId?.let { fields["channel_id"] = it }
                    app.api.multipart("/v1/posts", fields, photos.toList())
                    app.say("Posted")
                    nav.back()
                }
            })
    }
}

// ---------------------------------------------------------------- channels

/** Channels I follow, search, and start one (verified accounts). */
@Composable
fun ChannelsScreen(nav: NavHostController) {
    val app = LocalApp.current
    var q by remember { mutableStateOf("") }
    var creating by remember { mutableStateOf(false) }
    val mine = rememberLoader("my-channels") { app.api.list("/v1/channels/mine").objects() }
    var found by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    LaunchedEffect(q) {
        delay(300)
        found = runCatching { app.api.list("/v1/channels?q=" + URLEncoder.encode(q.trim(), "UTF-8")).objects() }.getOrDefault(emptyList())
    }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("Channels", onBack = { nav.back() }) {
            TextButton(onClick = { creating = true }) { Text("+ New channel", color = Mx.Blue, fontWeight = FontWeight.Bold) }
        }
        LazyColumn(contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Field(q, { q = it }, "Find a channel (name or @handle)", tag = "channel-search") }
            val following = mine.data.orEmpty()
            if (q.isBlank() && following.isNotEmpty()) {
                item { Text("Following", fontWeight = FontWeight.Bold) }
                items(following, key = { "f" + it.str("id") }) { ChannelRow(it, nav) }
            }
            item { Text(if (q.isBlank()) "Popular" else "Results", fontWeight = FontWeight.Bold) }
            if (found.isEmpty()) item { Text(if (q.isBlank()) "No channels yet. Start the first one!" else "No channel found.", color = Mx.Muted) }
            items(found, key = { "s" + it.str("id") }) { ChannelRow(it, nav) }
        }
    }
    if (creating) CreateChannelDialog(onDismiss = { creating = false }) { id -> creating = false; nav.navigate(Routes.channel(id)) }
}

@Composable
private fun ChannelRow(c: JSONObject, nav: NavHostController) {
    Card(Modifier.clickable { nav.navigate(Routes.channel(c.str("id"))) }.testTag("channel-${c.str("handle")}")) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Avatar(c.str("name"), 44.dp, key = c.str("id"))
            Column(Modifier.weight(1f)) {
                Text(c.str("name"), fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text("@${c.str("handle")} · ${c.optInt("followers")} followers", fontSize = 12.sp, color = Mx.Muted)
            }
            if (c.optBoolean("following")) Text("Following", fontSize = 12.sp, color = Mx.Green, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun CreateChannelDialog(onDismiss: () -> Unit, onCreated: (String) -> Unit) {
    val app = LocalApp.current
    var name by remember { mutableStateOf("") }
    var handle by remember { mutableStateOf("") }
    var about by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New channel") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("You and admins you choose post; followers read, like and comment. Needs a verified account (level 2).", fontSize = 13.sp, color = Mx.Muted)
                Field(name, { name = it.take(60); if (handle.isEmpty() || handle == slug(name.dropLast(1))) handle = slug(name) }, "Channel name", tag = "channel-name")
                Field(handle, { handle = slug(it) }, "Handle (@…)", tag = "channel-handle")
                Field(about, { about = it.take(500) }, "What it's about", singleLine = false, minLines = 2)
                error?.let { pg.mcxus.app.ui.ErrorBubble(it) { error = null } }
            }
        },
        confirmButton = {
            TextButton(enabled = name.length >= 2 && handle.length >= 3, onClick = {
                app.launch(onError = { error = it }) {
                    val c = app.api.post("/v1/channels", JSONObject().put("name", name.trim()).put("handle", handle).put("description", about.trim()))
                    onCreated(c.str("id"))
                }
            }) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

private fun slug(text: String): String = text.lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-').take(30)

/** A channel: about, follow, its posts; the owner and admins can post. */
@Composable
fun ChannelScreen(nav: NavHostController, channelId: String) {
    val app = LocalApp.current
    var refresh by remember { mutableIntStateOf(0) }
    val channel = rememberLoader(channelId, refresh) { app.api.obj("/v1/channels/$channelId") }
    val posts = rememberLoader("channel-posts", channelId, refresh) { app.api.list("/v1/channels/$channelId/posts").objects() }
    var reporting by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        val c = channel.data
        Header(c?.str("name") ?: "Channel", onBack = { nav.back() }) {
            if (c != null && c.isNull("role")) TextButton(onClick = { reporting = true }) { Text("Report", color = Mx.Muted) }
        }
        if (c == null) { if (channel.error != null) Empty(channel.error!!) else Loading(); return@Column }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                Card(Modifier.padding(horizontal = 14.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Avatar(c.str("name"), 56.dp, key = c.str("id"))
                        Column(Modifier.weight(1f)) {
                            Text(c.str("name"), fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
                            Text("@${c.str("handle")} · ${c.optInt("followers")} followers", fontSize = 12.sp, color = Mx.Muted)
                        }
                    }
                    if (c.str("description").isNotEmpty()) Text(c.str("description"), Modifier.padding(top = 8.dp), fontSize = 14.sp)
                    Spacer(Modifier.height(10.dp))
                    val role = if (c.isNull("role")) "" else c.str("role")
                    if (role.isNotEmpty()) {
                        BigButton("Write a post", onClick = { nav.navigate(Routes.newPost(channelId)) }, modifier = Modifier.testTag("channel-post"))
                        Text(if (role == "owner") "You own this channel" else "You are an admin", fontSize = 12.sp, color = Mx.Muted, modifier = Modifier.padding(top = 6.dp))
                    } else {
                        val following = c.optBoolean("following")
                        LineButton(if (following) "Following ✓  (tap to unfollow)" else "Follow", {
                            app.launch {
                                channel.data = if (following) JSONObject(app.api.delete("/v1/channels/$channelId/follow")) else app.api.post("/v1/channels/$channelId/follow")
                            }
                        }, Modifier.fillMaxWidth().testTag("follow"))
                    }
                }
            }
            val list = posts.data
            if (list == null) item { Loading() } else if (list.isEmpty()) item { Empty("No posts yet.") }
            else items(list, key = { it.str("id") }) { p -> PostCard(p, nav, { refresh++ }) }
        }
    }
    if (reporting) ReportDialog("channel", channelId) { reporting = false }
}
