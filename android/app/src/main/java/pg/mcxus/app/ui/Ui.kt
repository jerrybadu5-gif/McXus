package pg.mcxus.app.ui

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView

/** Tiny helpers to build screens in code: no XML layouts, no UI framework. */
object Ui {
    const val GREEN = 0xFF0F5C4C.toInt()
    const val GOLD = 0xFFE8A33D.toInt()
    const val INK = 0xFF1F2421.toInt()
    const val MUTED = 0xFF5F6B66.toInt()
    const val CARD = Color.WHITE
    const val LINE = 0xFFE3DFD6.toInt()
    const val RED = 0xFFB3261E.toInt()

    fun Context.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    fun column(ctx: Context, padding: Int = 16, vararg children: View): LinearLayout =
        LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(ctx.dp(padding), ctx.dp(padding), ctx.dp(padding), ctx.dp(padding))
            children.forEach { addView(it) }
        }

    fun row(ctx: Context, vararg children: View): LinearLayout =
        LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            children.forEach { addView(it) }
        }

    fun scroll(ctx: Context, content: View): ScrollView = ScrollView(ctx).apply {
        isFillViewport = true
        addView(content)
    }

    fun text(ctx: Context, s: CharSequence, size: Float = 15f, bold: Boolean = false, color: Int = INK): TextView =
        TextView(ctx).apply {
            text = s
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(typeface, Typeface.BOLD)
            setPadding(0, ctx.dp(3), 0, ctx.dp(3))
        }

    fun title(ctx: Context, s: String) = text(ctx, s, 20f, bold = true)

    fun muted(ctx: Context, s: CharSequence) = text(ctx, s, 13f, color = MUTED)

    fun button(ctx: Context, label: String, primary: Boolean = true, onClick: () -> Unit): Button =
        Button(ctx).apply {
            text = label
            isAllCaps = false
            textSize = 15f
            setTextColor(if (primary) Color.WHITE else GREEN)
            background = rounded(if (primary) GREEN else Color.WHITE, ctx.dp(10), if (primary) 0 else GREEN, ctx.dp(1))
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ctx.dp(48)).apply {
                topMargin = ctx.dp(6)
                bottomMargin = ctx.dp(6)
            }
        }

    fun input(ctx: Context, hint: String, type: Int = InputType.TYPE_CLASS_TEXT, value: String = ""): EditText =
        EditText(ctx).apply {
            this.hint = hint
            inputType = type
            setText(value)
            textSize = 16f
            setSingleLine(type and InputType.TYPE_TEXT_FLAG_MULTI_LINE == 0)
        }

    fun numberInput(ctx: Context, hint: String, value: String = "", decimal: Boolean = false) = input(
        ctx, hint,
        InputType.TYPE_CLASS_NUMBER or (if (decimal) InputType.TYPE_NUMBER_FLAG_DECIMAL else 0), value,
    )

    fun label(ctx: Context, s: String) = text(ctx, s, 13f, bold = true, color = MUTED).apply {
        setPadding(0, ctx.dp(10), 0, 0)
    }

    fun card(ctx: Context, vararg children: View, onClick: (() -> Unit)? = null): LinearLayout =
        column(ctx, 12, *children).apply {
            background = rounded(CARD, ctx.dp(12), LINE, ctx.dp(1))
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { bottomMargin = ctx.dp(10) }
            if (onClick != null) {
                isClickable = true
                setOnClickListener { onClick() }
            }
        }

    fun image(ctx: Context, sizeDp: Int): ImageView = ImageView(ctx).apply {
        scaleType = ImageView.ScaleType.CENTER_CROP
        setBackgroundColor(LINE)
        layoutParams = LinearLayout.LayoutParams(ctx.dp(sizeDp), ctx.dp(sizeDp)).apply { rightMargin = ctx.dp(10) }
    }

    fun <T> spinner(ctx: Context, items: List<T>, label: (T) -> String, onSelect: (T) -> Unit): Spinner =
        Spinner(ctx).apply {
            adapter = ArrayAdapter(ctx, android.R.layout.simple_spinner_dropdown_item, items.map(label))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) = onSelect(items[pos])
                override fun onNothingSelected(p: AdapterView<*>?) = Unit
            }
        }

    fun weight(view: View, w: Float = 1f): View = view.apply {
        layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, w)
    }

    fun rounded(fill: Int, radius: Int, stroke: Int = 0, strokeWidth: Int = 0) = GradientDrawable().apply {
        setColor(fill)
        cornerRadius = radius.toFloat()
        if (strokeWidth > 0) setStroke(strokeWidth, stroke)
    }

    fun chip(ctx: Context, s: String, color: Int = GREEN) = text(ctx, s, 12f, bold = true, color = color).apply {
        background = rounded(Color.WHITE, ctx.dp(20), color, ctx.dp(1))
        setPadding(ctx.dp(8), ctx.dp(2), ctx.dp(8), ctx.dp(2))
    }
}
