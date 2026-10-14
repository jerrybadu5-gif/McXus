package pg.mcxus.app.chat

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/** A message as kept on this phone after decryption. [payload] is the JSON the sender wrote (see [Payload]). */
data class LocalMessage(
    val localId: Long,
    val conversationId: String,
    val serverId: Long?,
    val mine: Boolean,
    val payload: String,
    val at: Long,
    val unread: Boolean,
)

/**
 * Decrypted messages live only on this phone, in the app's private database (the server keeps ciphertext for
 * 30 days and cannot read it). One database per signed-in user. Backups are off in the manifest.
 */
class ChatStore(context: Context, userId: String) :
    SQLiteOpenHelper(context, "chat-$userId.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """CREATE TABLE messages (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 conv TEXT NOT NULL,
                 server_id INTEGER UNIQUE,
                 mine INTEGER NOT NULL,
                 payload TEXT NOT NULL,
                 at INTEGER NOT NULL,
                 unread INTEGER NOT NULL DEFAULT 0)""",
        )
        db.execSQL("CREATE INDEX ix_messages_conv ON messages(conv, at)")
        db.execSQL("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun get(key: String): String? =
        readableDatabase.rawQuery("SELECT v FROM kv WHERE k = ?", arrayOf(key)).use { if (it.moveToFirst()) it.getString(0) else null }

    fun put(key: String, value: String) {
        writableDatabase.insertWithOnConflict(
            "kv", null, ContentValues().apply { put("k", key); put("v", value) }, SQLiteDatabase.CONFLICT_REPLACE,
        )
    }

    /** Insert once per server message id (a repeated sync never duplicates). */
    fun add(conversationId: String, serverId: Long?, mine: Boolean, payload: String, at: Long, unread: Boolean) {
        writableDatabase.insertWithOnConflict(
            "messages", null,
            ContentValues().apply {
                put("conv", conversationId)
                if (serverId != null) put("server_id", serverId) else putNull("server_id")
                put("mine", if (mine) 1 else 0)
                put("payload", payload)
                put("at", at)
                put("unread", if (unread) 1 else 0)
            },
            SQLiteDatabase.CONFLICT_IGNORE,
        )
    }

    fun messages(conversationId: String): List<LocalMessage> =
        readableDatabase.rawQuery(
            "SELECT id, conv, server_id, mine, payload, at, unread FROM messages WHERE conv = ? ORDER BY at, id",
            arrayOf(conversationId),
        ).use { c ->
            buildList {
                while (c.moveToNext()) {
                    add(
                        LocalMessage(
                            c.getLong(0), c.getString(1), if (c.isNull(2)) null else c.getLong(2), c.getInt(3) == 1,
                            c.getString(4), c.getLong(5), c.getInt(6) == 1,
                        ),
                    )
                }
            }
        }

    /** conversation id -> (last message payload, time, unread count). */
    fun summaries(): Map<String, Triple<String, Long, Int>> =
        readableDatabase.rawQuery(
            """SELECT m.conv, m.payload, m.at, (SELECT COUNT(*) FROM messages u WHERE u.conv = m.conv AND u.unread = 1)
               FROM messages m
               WHERE m.id = (SELECT id FROM messages x WHERE x.conv = m.conv ORDER BY at DESC, id DESC LIMIT 1)""",
            null,
        ).use { c ->
            buildMap { while (c.moveToNext()) put(c.getString(0), Triple(c.getString(1), c.getLong(2), c.getInt(3))) }
        }

    fun markRead(conversationId: String) {
        writableDatabase.execSQL("UPDATE messages SET unread = 0 WHERE conv = ? AND unread = 1", arrayOf(conversationId))
    }
}
