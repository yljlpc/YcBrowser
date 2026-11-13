"""界面中文化：把 Qt 标准对话框按钮替换为中文。

Qt 的标准按钮（Ok / Cancel / Close / Yes / No）在中文系统上是否显示中文
取决于运行环境的 locale，在部分发行版上仍是英文。为保证「界面零英文残留」，
这里统一改用自定义文本的按钮。

用法：
    from .zh import zh_buttons, zh_msg_question, zh_msg_info, zh_msg_warning

    box = zh_buttons(dlg, ok="确定", cancel="取消")
    if zh_msg_question(dlg, "标题", "内容"):
        ...
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialogButtonBox, QMessageBox, QPushButton

# 标准按钮 → 中文文本
ZH_BUTTON_TEXT = {
    QDialogButtonBox.StandardButton.Ok: "确定",
    QDialogButtonBox.StandardButton.Cancel: "取消",
    QDialogButtonBox.StandardButton.Close: "关闭",
    QDialogButtonBox.StandardButton.Yes: "是",
    QDialogButtonBox.StandardButton.No: "否",
    QDialogButtonBox.StandardButton.Save: "保存",
    QDialogButtonBox.StandardButton.Apply: "应用",
    QDialogButtonBox.StandardButton.Reset: "重置",
    QDialogButtonBox.StandardButton.Help: "帮助",
    QDialogButtonBox.StandardButton.Abort: "中止",
    QDialogButtonBox.StandardButton.Retry: "重试",
    QDialogButtonBox.StandardButton.Ignore: "忽略",
    QDialogButtonBox.StandardButton.Discard: "放弃",
}

# 消息框按钮 → 中文文本
ZH_MSG_TEXT = {
    QMessageBox.StandardButton.Ok: "确定",
    QMessageBox.StandardButton.Cancel: "取消",
    QMessageBox.StandardButton.Close: "关闭",
    QMessageBox.StandardButton.Yes: "确定",
    QMessageBox.StandardButton.No: "取消",
    QMessageBox.StandardButton.Save: "保存",
    QMessageBox.StandardButton.Apply: "应用",
    QMessageBox.StandardButton.Reset: "重置",
    QMessageBox.StandardButton.Help: "帮助",
    QMessageBox.StandardButton.Abort: "中止",
    QMessageBox.StandardButton.Retry: "重试",
    QMessageBox.StandardButton.Ignore: "忽略",
    QMessageBox.StandardButton.Discard: "放弃",
}


def zh_buttons(parent, ok="确定", cancel="取消", close=None, extra=None,
               with_ok=True, with_cancel=True):
    """构造带中文文本的按钮盒。

    - `ok` / `cancel` / `close` 为 None 或空串表示不显示该按钮；
    - 默认显示「确定 + 取消」，只传 close=... 且 with_ok=False 可得「仅关闭」；
    - `extra` 可传 [(文本, 角色), ...] 追加自定义按钮。
    返回 QDialogButtonBox（已接好 accepted / rejected 信号）。
    """
    std = QDialogButtonBox.StandardButton.NoButton
    if with_ok and ok:
        std |= QDialogButtonBox.StandardButton.Ok
    if with_cancel and cancel:
        std |= QDialogButtonBox.StandardButton.Cancel
    if close:
        std |= QDialogButtonBox.StandardButton.Close

    box = QDialogButtonBox(parent)
    box.setStandardButtons(std)
    for btn in box.buttons():
        std_btn = box.standardButton(btn)
        text = ""
        if std_btn == QDialogButtonBox.StandardButton.Ok:
            text = ok or ""
        elif std_btn == QDialogButtonBox.StandardButton.Cancel:
            text = cancel or ""
        elif std_btn == QDialogButtonBox.StandardButton.Close:
            text = close or "关闭"
        else:
            text = ZH_BUTTON_TEXT.get(std_btn, "")
        if text:
            btn.setText(text)
    if extra:
        for text, role in extra:
            box.addButton(text, role)
    box.accepted.connect(parent.accept)
    box.rejected.connect(parent.reject)
    return box


def zh_msg_box(parent, icon, title, text, buttons=None, default=None):
    """带中文按钮的消息框。

    返回被点击按钮对应的 StandardButton；无返回值则为 None。
    """
    if buttons is None:
        buttons = QMessageBox.StandardButton.Ok
    if default is None:
        default = QMessageBox.StandardButton.NoButton
    box = QMessageBox(icon, title, text, buttons, parent)
    for btn in box.buttons():
        std = box.standardButton(btn)
        t = ZH_MSG_TEXT.get(std)
        if t:
            btn.setText(t)
    box.setDefaultButton(default)
    return box.exec()


def zh_msg_question(parent, title, text):
    """确认框（确定 / 取消），返回 True 表示确定。"""
    r = zh_msg_box(
        parent, QMessageBox.Icon.Question, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return r == QMessageBox.StandardButton.Yes


def zh_msg_info(parent, title, text):
    return zh_msg_box(parent, QMessageBox.Icon.Information, title, text)


def zh_msg_warning(parent, title, text):
    return zh_msg_box(parent, QMessageBox.Icon.Warning, title, text)


def zh_msg_error(parent, title, text):
    return zh_msg_box(parent, QMessageBox.Icon.Critical, title, text)


def apply_zh_to_dialog(dlg, buttons=None):
    """把已存在的对话框里的按钮文本改成中文（用于系统自带对话框）。"""
    for btn in dlg.findChildren(QPushButton):
        std = dlg.standardButton(btn)
        if std is not None:
            t = ZH_BUTTON_TEXT.get(std)
            if t:
                btn.setText(t)
    return dlg
