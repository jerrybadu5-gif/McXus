package pg.mcxus.app.ui.screens

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavHostController
import org.json.JSONObject
import pg.mcxus.app.LocalApp
import pg.mcxus.app.Routes
import pg.mcxus.app.back
import pg.mcxus.app.chat.ChatEngine
import pg.mcxus.app.ui.Avatar
import pg.mcxus.app.ui.BigButton
import pg.mcxus.app.ui.Empty
import pg.mcxus.app.ui.Field
import pg.mcxus.app.ui.Header
import pg.mcxus.app.ui.Ic
import pg.mcxus.app.ui.LineButton
import pg.mcxus.app.ui.Loading
import pg.mcxus.app.ui.Note
import pg.mcxus.app.ui.PeopleSearch
import pg.mcxus.app.ui.Tag
import pg.mcxus.app.ui.rememberLoader
import pg.mcxus.app.ui.str
import pg.mcxus.app.ui.theme.Mx

/** Someone who can be added: from existing chats or found by phone number. */
private data class Candidate(val id: String, val name: String)

/** The people picker shared by New group and Add people. */
@Composable
private fun PeoplePicker(
    candidates: List<Candidate>,
    selected: List<String>,
    onToggle: (String) -> Unit,
    onFound: (Candidate) -> Unit,
    modifier: Modifier = Modifier,
) {
    val app = LocalApp.current
    var phone by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        PeopleSearch(phone, { phone = it }, onPick = { found ->
            onFound(Candidate(found.str("id"), found.str("name")))
            phone = ""
        }, label = "Add by name or mobile number", tag = "group-phone")
        if (candidates.isEmpty()) {
            Text("People you chat with appear here. You can also add anyone by name or mobile number.", color = Mx.Muted, fontSize = 13.sp)
        }
        // Typing also filters the people you already chat with (any case).
        val words = phone.trim().lowercase().split(Regex("\\s+")).filter { it.isNotEmpty() && !it.all(Char::isDigit) }
        Column(Modifier.clip(RoundedCornerShape(16.dp)).background(Color.White)) {
            candidates.filter { c -> words.all { c.name.lowercase().contains(it) } || c.id in selected }.forEach { c ->
                Row(
                    Modifier.fillMaxWidth().clickable { onToggle(c.id) }.padding(horizontal = 12.dp, vertical = 8.dp).testTag("pick-${c.name}"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Avatar(c.name, 40.dp, key = c.id)
                    Text(c.name, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Checkbox(c.id in selected, { onToggle(c.id) }, colors = CheckboxDefaults.colors(checkedColor = Mx.Blue))
                }
                HorizontalDivider(color = Mx.LineSoft)
            }
        }
    }
}

private fun explainMissing(engine: ChatEngine, result: ChatEngine.AddResult, names: Map<String, String>): String? =
    if (result.withoutApp.isEmpty()) null
    else result.withoutApp.joinToString(", ") { names[it] ?: "someone" } +
        " could not be added yet: they need to open the new McXus once. Add them later from Group info."

@Composable
fun NewGroupScreen(nav: NavHostController) {
    val app = LocalApp.current
    val engine = app.chat ?: run { Loading(); return }
    val conversations by engine.conversations.collectAsState()
    var title by remember { mutableStateOf("") }
    val selected = remember { mutableStateListOf<String>() }
    val extra = remember { mutableStateListOf<Candidate>() }
    var busy by remember { mutableStateOf(false) }
    val candidates = (conversations.filter { !it.isGroup && it.peer != null }.map { Candidate(it.peer!!.id, it.peer.name) } + extra)
        .distinctBy { it.id }

    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("New group", onBack = { nav.back() })
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Field(title, { title = it.take(80) }, "Group name, e.g. Eriku Youth Group", tag = "group-title") }
            item { Text("Members (${selected.size} chosen, up to 255)", fontWeight = FontWeight.Bold) }
            item {
                PeoplePicker(candidates, selected, { id -> if (id in selected) selected.remove(id) else selected.add(id) }, { c ->
                    if (extra.none { it.id == c.id }) extra.add(c)
                    if (c.id !in selected) selected.add(c.id)
                })
            }
            item { Note("Group messages are end-to-end encrypted. McXus can see the group name and who is in it, not the messages.", icon = Ic.Lock) }
        }
        BigButton("Create group", busy = busy, enabled = title.isNotBlank(), modifier = Modifier.navigationBarsPadding().padding(16.dp).testTag("create-group"), onClick = {
            busy = true
            app.launch(onDone = { busy = false }) {
                val (conv, result) = engine.createGroup(title.trim(), selected.toList())
                explainMissing(engine, result, candidates.associate { it.id to it.name })?.let { app.say(it, error = true) }
                nav.navigate(Routes.chat(conv)) { popUpTo(Routes.HOME) }
            }
        })
    }
}

@Composable
fun GroupInfoScreen(nav: NavHostController, conversationId: String) {
    val app = LocalApp.current
    val engine = app.chat ?: run { Loading(); return }
    val conversations by engine.conversations.collectAsState()
    var refresh by remember { mutableIntStateOf(0) }
    val info = rememberLoader(conversationId, refresh) { engine.groupInfo(conversationId, refresh = true) }
    val me = engine.userId
    var adding by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf(false) }
    var leaving by remember { mutableStateOf(false) }
    var menuFor by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun act(block: suspend () -> Unit) {
        busy = true
        app.launch(onDone = { busy = false; refresh++ }) { block() }
    }

    Column(Modifier.fillMaxSize().background(Mx.Bg)) {
        Header("Group info", onBack = { nav.back() })
        val g = info.data
        if (g == null) {
            if (info.error != null) Empty(info.error!!) else Loading()
            return@Column
        }
        val amAdmin = g.members.any { it.id == me && it.role == "admin" }
        LazyColumn(Modifier.weight(1f), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(84.dp).clip(RoundedCornerShape(42.dp)).background(Mx.Navy), contentAlignment = Alignment.Center) {
                        Icon(Ic.Group, null, tint = Mx.Gold, modifier = Modifier.size(42.dp))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(g.title, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold)
                        if (amAdmin) IconButton(onClick = { renaming = true }) { Icon(Ic.Edit, "Rename group", tint = Mx.Blue) }
                    }
                    Text("Group · ${g.members.size} members · end-to-end encrypted", color = Mx.Muted, fontSize = 13.sp)
                }
            }
            if (amAdmin) item {
                LineButton("Add people", { adding = true }, Modifier.fillMaxWidth().testTag("add-people"))
            }
            item { Text("Members", fontWeight = FontWeight.Bold) }
            item {
                Column(Modifier.clip(RoundedCornerShape(16.dp)).background(Color.White)) {
                    g.members.forEach { m ->
                        Box {
                            Row(
                                Modifier.fillMaxWidth().clickable(enabled = amAdmin && m.id != me) { menuFor = m.id }
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(12.dp),
                            ) {
                                Avatar(m.name, 40.dp, key = m.id)
                                Text(if (m.id == me) "${m.name} (you)" else m.name, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f),
                                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                                if (m.role == "admin") Tag("Admin", Mx.GreenSoft, Mx.GreenInk)
                            }
                            DropdownMenu(menuFor == m.id, onDismissRequest = { menuFor = null }) {
                                DropdownMenuItem(text = { Text(if (m.role == "admin") "Remove as admin" else "Make admin") }, onClick = {
                                    menuFor = null
                                    act { engine.setRole(conversationId, m.id, if (m.role == "admin") "member" else "admin") }
                                })
                                DropdownMenuItem(text = { Text("Remove from group", color = Mx.Red) }, onClick = {
                                    menuFor = null
                                    act { engine.removeMembers(conversationId, listOf(m.id)); app.say("${m.name} removed") }
                                })
                            }
                        }
                        HorizontalDivider(color = Mx.LineSoft)
                    }
                }
            }
            item {
                LineButton("Verify encryption (safety number)", {
                    app.say(engine.safetyNumber(conversationId)?.let { "Safety number: $it" } ?: "Not available yet")
                }, Modifier.fillMaxWidth())
            }
            item { LineButton("Leave group", { leaving = true }, Modifier.fillMaxWidth().testTag("leave-group"), color = Mx.Red) }
        }

        if (adding) {
            val selected = remember { mutableStateListOf<String>() }
            val extra = remember { mutableStateListOf<Candidate>() }
            val inGroup = g.members.map { it.id }.toSet()
            val candidates = (conversations.filter { !it.isGroup && it.peer != null }.map { Candidate(it.peer!!.id, it.peer.name) } + extra)
                .distinctBy { it.id }.filter { it.id !in inGroup }
            AlertDialog(
                onDismissRequest = { adding = false },
                title = { Text("Add people") },
                text = {
                    LazyColumn {
                        item {
                            PeoplePicker(candidates, selected, { id -> if (id in selected) selected.remove(id) else selected.add(id) }, { c ->
                                if (c.id in inGroup) app.say("${c.name} is already in the group")
                                else { if (extra.none { it.id == c.id }) extra.add(c); if (c.id !in selected) selected.add(c.id) }
                            })
                        }
                    }
                },
                confirmButton = {
                    TextButton(enabled = selected.isNotEmpty() && !busy, onClick = {
                        adding = false
                        val names = candidates.associate { it.id to it.name }
                        act {
                            val r = engine.addMembers(conversationId, selected.toList())
                            explainMissing(engine, r, names)?.let { app.say(it, error = true) } ?: app.say("${r.added.size} added")
                        }
                    }) { Text("Add") }
                },
                dismissButton = { TextButton(onClick = { adding = false }) { Text("Cancel") } },
            )
        }
        if (renaming) {
            var name by remember { mutableStateOf(g.title) }
            AlertDialog(
                onDismissRequest = { renaming = false },
                title = { Text("Group name") },
                text = { Field(name, { name = it.take(80) }, "Group name") },
                confirmButton = { TextButton(onClick = { renaming = false; act { engine.rename(conversationId, name.trim()) } }) { Text("Save") } },
                dismissButton = { TextButton(onClick = { renaming = false }) { Text("Cancel") } },
            )
        }
        if (leaving) {
            AlertDialog(
                onDismissRequest = { leaving = false },
                text = { Text("Leave \"${g.title}\"? You will stop receiving its messages.") },
                confirmButton = {
                    TextButton(onClick = {
                        leaving = false
                        busy = true
                        app.launch(onDone = { busy = false }) {
                            engine.leaveGroup(conversationId)
                            nav.navigate(Routes.HOME) { popUpTo(0) }
                        }
                    }) { Text("Leave", color = Mx.Red) }
                },
                dismissButton = { TextButton(onClick = { leaving = false }) { Text("Cancel") } },
            )
        }
    }
}
