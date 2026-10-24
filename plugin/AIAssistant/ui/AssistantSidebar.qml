import QtQuick 2.7
import QtQuick.Controls 2.0
import QtQuick.Layouts 1.3

import UM 1.2 as UM

Rectangle {
    id: root
    color: UM.Theme.getColor("sidebar")

    property color borderColor: UM.Theme.getColor("sidebar_lining")
    property color textColor: UM.Theme.getColor("text")
    property color mutedColor: UM.Theme.getColor("text_inactive")
    property color accentColor: UM.Theme.getColor("action_button_active")

    ListModel {
        id: messages
        ListElement {
            role: "assistant"
            text: "Я готов помочь настроить печать и проанализировать текущую модель."
        }
    }

    function addUserMessage(text) {
        messages.append({"role": "user", "text": text})
    }

    function addAssistantMessage(text) {
        messages.append({"role": "assistant", "text": text})
    }

    Connections {
        target: aiAssistantBridge
        onReplyReady: function(reply) {
            var text = reply || "LLM вернула пустой ответ."
            addAssistantMessage(text)
            messageList.positionViewAtEnd()
        }
        onRequestFailed: function(error) {
            addAssistantMessage("Ошибка: " + (error || "неизвестная ошибка"))
            messageList.positionViewAtEnd()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UM.Theme.getSize("sidebar_margin").width
        spacing: UM.Theme.getSize("default_margin").height

        Label {
            Layout.fillWidth: true
            text: "AI Assistant"
            color: textColor
            font: UM.Theme.getFont("large")
            elide: Text.ElideRight
        }

        Label {
            Layout.fillWidth: true
            text: "Анализ модели и настройка печати"
            color: mutedColor
            font: UM.Theme.getFont("small")
            wrapMode: Text.WordWrap
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "transparent"
            border.width: 1
            border.color: borderColor
            radius: 3

            ListView {
                id: messageList
                anchors.fill: parent
                anchors.margins: UM.Theme.getSize("default_margin").width
                model: messages
                spacing: UM.Theme.getSize("default_margin").height
                clip: true

                delegate: Column {
                    width: messageList.width
                    spacing: 2

                    Label {
                        text: role === "user" ? "Вы" : "AI Assistant"
                        color: role === "user" ? accentColor : mutedColor
                        font: UM.Theme.getFont("small")
                    }

                    Label {
                        width: parent.width
                        text: model.text
                        color: textColor
                        font: UM.Theme.getFont("default")
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }

        Label {
            Layout.fillWidth: true
            text: aiAssistantBridge ? aiAssistantBridge.status : "Готов к работе"
            color: mutedColor
            font: UM.Theme.getFont("small")
            elide: Text.ElideRight
        }

        Rectangle {
            Layout.fillWidth: true
            visible: aiAssistantBridge && aiAssistantBridge.confirmationPending
            color: "transparent"
            border.width: 1
            border.color: accentColor
            radius: 3
            implicitHeight: confirmationColumn.implicitHeight + 2 * UM.Theme.getSize("default_margin").height

            ColumnLayout {
                id: confirmationColumn
                anchors.fill: parent
                anchors.margins: UM.Theme.getSize("default_margin").width
                spacing: UM.Theme.getSize("default_margin").height

                Label {
                    Layout.fillWidth: true
                    text: "Требуется подтверждение действия"
                    color: accentColor
                    font: UM.Theme.getFont("default")
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: aiAssistantBridge ? aiAssistantBridge.confirmationTool : ""
                    color: textColor
                    font: UM.Theme.getFont("small")
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text: aiAssistantBridge ? aiAssistantBridge.confirmationArguments : ""
                    color: mutedColor
                    font: UM.Theme.getFont("small")
                    wrapMode: Text.WordWrap
                    maximumLineCount: 8
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: UM.Theme.getSize("default_margin").width

                    Button {
                        Layout.fillWidth: true
                        text: "Выполнить"
                        onClicked: aiAssistantBridge.confirmAction()
                    }

                    Button {
                        Layout.fillWidth: true
                        text: "Отмена"
                        onClicked: aiAssistantBridge.cancelAction()
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: UM.Theme.getSize("default_margin").width

            TextField {
                id: messageInput
                Layout.fillWidth: true
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                placeholderText: "Например: кронштейн под нагрузку 50 кг"
                selectByMouse: true
                onAccepted: sendButton.clicked()
            }

            Button {
                id: sendButton
                text: "Отправить"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                onClicked: {
                    var text = messageInput.text.trim()
                    if (!text || !aiAssistantBridge || aiAssistantBridge.busy) {
                        return
                    }
                    addUserMessage(text)
                    aiAssistantBridge.sendMessage(text)
                    messageInput.clear()
                    messageList.positionViewAtEnd()
                }
            }
        }

        Button {
            Layout.fillWidth: true
            enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
            text: "Проанализировать текущую модель"
            onClicked: {
                if (!aiAssistantBridge || aiAssistantBridge.busy) {
                    return
                }
                addUserMessage("Проанализируй текущую модель")
                aiAssistantBridge.sendMessage("Проанализируй текущую модель")
                messageList.positionViewAtEnd()
            }
        }
    }
}
