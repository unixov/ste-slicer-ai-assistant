import QtQuick 2.7
import QtQuick.Controls 2.0
import QtQuick.Layouts 1.3

import UM 1.2 as UM

Rectangle {
    id: root
    color: UM.Theme.getColor("sidebar")

    // ------------------------------------------------------------------ //
    // Theme shortcuts
    // ------------------------------------------------------------------ //
    property color borderColor:   UM.Theme.getColor("sidebar_lining")
    property color textColor:     UM.Theme.getColor("text")
    property color mutedColor:    UM.Theme.getColor("text_inactive")
    property color accentColor:   UM.Theme.getColor("action_button_active")

    // ------------------------------------------------------------------ //
    // Structural analysis state (parsed from bridge JSON property)
    // ------------------------------------------------------------------ //
    property var  structuralData:     ({})
    property bool hasStructural:      Object.keys(root.structuralData).length > 0
    property bool structExpanded:     true

    // ------------------------------------------------------------------ //
    // Chat message model
    // ------------------------------------------------------------------ //
    ListModel {
        id: messages
        ListElement {
            role:    "assistant"
            text:    "Готов к работе. Загрузите модель — я автоматически выполню структурный анализ и предложу оптимальные настройки."
            isError: false
        }
    }

    function addUserMessage(txt)     { messages.append({ role: "user",      text: txt, isError: false }) }
    function addAssistantMessage(txt){ messages.append({ role: "assistant",  text: txt, isError: false }) }
    function addErrorMessage(txt)    { messages.append({ role: "assistant",  text: txt, isError: true  }) }

    // ------------------------------------------------------------------ //
    // Risk score helpers
    // ------------------------------------------------------------------ //
    function riskColor(score) {
        if (score >= 7) return "#e74c3c"
        if (score >= 4) return "#f39c12"
        return "#27ae60"
    }
    function riskLabel(score) {
        if (score >= 8) return "КРИТ"
        if (score >= 6) return "ВЫСК"
        if (score >= 4) return "УМ"
        return "НЗК"
    }

    // Human-readable names for confirmation panel
    function toolHumanName(n) {
        var m = {
            "scene.arrange_all":           "Авторасстановка моделей",
            "scene.move_object":           "Переместить объект",
            "scene.rotate_object":         "Повернуть объект",
            "settings.apply":              "Применить настройки",
            "backend.start_slicing":       "Запустить слайсинг",
            "export.scene":                "Экспортировать сцену"
        }
        return m[n] || n
    }

    // ------------------------------------------------------------------ //
    // Bridge connections
    // ------------------------------------------------------------------ //
    Connections {
        target: aiAssistantBridge

        onReplyReady: {
            addAssistantMessage(aiAssistantBridge.lastReply || "LLM вернула пустой ответ.")
            messageList.positionViewAtEnd()
        }
        onRequestFailed: {
            addErrorMessage("Ошибка: " + (aiAssistantBridge.lastError || "неизвестная ошибка"))
            messageList.positionViewAtEnd()
        }
        onModelLoadedSignal: {
            addAssistantMessage("Обнаружена новая модель — запускаю структурный анализ...")
            messageList.positionViewAtEnd()
        }
        onStructuralAnalysisReady: {
            try {
                root.structuralData = JSON.parse(aiAssistantBridge.lastStructuralResult)
                root.structExpanded  = true
            } catch(e) {
                root.structuralData = {}
            }
        }
    }

    // ------------------------------------------------------------------ //
    // Root layout
    // ------------------------------------------------------------------ //
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: UM.Theme.getSize("sidebar_margin").width
        spacing: UM.Theme.getSize("default_margin").height

        // ============================================================== //
        // HEADER
        // ============================================================== //
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Column {
                Layout.fillWidth: true
                spacing: 2

                Label {
                    text:  "AI Assistant"
                    color: textColor
                    font:  UM.Theme.getFont("large")
                }
                Label {
                    width: parent.width
                    text:  (aiAssistantBridge ? aiAssistantBridge.status : "Инициализация...")
                    color: (aiAssistantBridge && aiAssistantBridge.busy) ? accentColor : mutedColor
                    font:  UM.Theme.getFont("small")
                    elide: Text.ElideRight
                }
            }

            // Animated busy dot
            Rectangle {
                width: 10; height: 10; radius: 5
                color:   (aiAssistantBridge && aiAssistantBridge.busy) ? accentColor : mutedColor
                opacity: (aiAssistantBridge && aiAssistantBridge.busy) ? 1.0 : 0.35

                SequentialAnimation on opacity {
                    running: aiAssistantBridge && aiAssistantBridge.busy
                    loops:   Animation.Infinite
                    NumberAnimation { to: 0.2; duration: 600 }
                    NumberAnimation { to: 1.0; duration: 600 }
                }
            }
        }

        // ============================================================== //
        // STRUCTURAL ANALYSIS PANEL  (killer feature card)
        // ============================================================== //
        Rectangle {
            Layout.fillWidth: true
            visible:          root.hasStructural
            color:            "transparent"
            border.width:     1
            border.color:     accentColor
            radius:           4
            // Height: header (always) + body (when expanded)
            implicitHeight:   saHeader.implicitHeight + 16 +
                              (root.structExpanded ? saBody.implicitHeight + 8 : 0)

            Behavior on implicitHeight { NumberAnimation { duration: 150 } }

            // --- card header row ---
            RowLayout {
                id: saHeader
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                spacing: 6

                Label {
                    Layout.fillWidth: true
                    text:  "Структурный анализ"
                    color: accentColor
                    font:  UM.Theme.getFont("default_bold")
                }

                // Profile badge
                Rectangle {
                    visible: root.structuralData.stress_profile !== undefined
                    color:   "#2c3e50"
                    radius:  3
                    width:   profileBadgeLabel.implicitWidth + 10
                    height:  profileBadgeLabel.implicitHeight + 4
                    Label {
                        id: profileBadgeLabel
                        anchors.centerIn: parent
                        text:  root.structuralData.stress_profile || ""
                        color: "#ecf0f1"
                        font:  UM.Theme.getFont("small")
                    }
                }

                // Expand / collapse toggle
                Label {
                    text:  root.structExpanded ? "▲" : "▼"
                    color: accentColor
                    font:  UM.Theme.getFont("small")
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.structExpanded = !root.structExpanded
                    }
                }
            }

            // --- card body (collapsible) ---
            Column {
                id: saBody
                anchors {
                    left:   parent.left;   right:  parent.right
                    top:    saHeader.bottom; margins: 8
                }
                spacing: 5
                visible: root.structExpanded
                opacity: root.structExpanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }

                // Stress zones
                Repeater {
                    model: root.structuralData.zones || []
                    delegate: RowLayout {
                        width: saBody.width
                        spacing: 6

                        // Risk badge
                        Rectangle {
                            width:  40; height: 18; radius: 3
                            color:  root.riskColor(modelData.risk_score)
                            Label {
                                anchors.centerIn: parent
                                text:  root.riskLabel(modelData.risk_score)
                                color: "white"
                                font.pixelSize: 9
                                font.bold: true
                            }
                        }

                        // Zone name
                        Label {
                            Layout.fillWidth: true
                            text:     modelData.label || ""
                            color:    textColor
                            font:     UM.Theme.getFont("small")
                            wrapMode: Text.WordWrap
                        }

                        // Score number
                        Label {
                            text:  modelData.risk_score + "/10"
                            color: root.riskColor(modelData.risk_score)
                            font:  UM.Theme.getFont("small")
                        }
                    }
                }

                // Divider
                Rectangle {
                    width: parent.width; height: 1
                    color: borderColor
                    visible: root.structuralData.orientation !== undefined
                }

                // Orientation recommendation
                Label {
                    width:   parent.width
                    visible: root.structuralData.orientation !== undefined &&
                             root.structuralData.orientation.action !== "keep"
                    text: root.structuralData.orientation
                          ? ("Поворот: ось " + (root.structuralData.orientation.axis || "").toUpperCase() +
                             " " + root.structuralData.orientation.angle_deg + "°" +
                             "  |  " + (root.structuralData.orientation.estimated_strength_gain || ""))
                          : ""
                    color:    accentColor
                    font:     UM.Theme.getFont("small")
                    wrapMode: Text.WordWrap
                }

                // Adaptive infill summary
                Label {
                    width:   parent.width
                    visible: root.structuralData.adaptive_infill !== undefined
                    text: root.structuralData.adaptive_infill
                          ? ("Заполнение: " +
                             root.structuralData.adaptive_infill.base_density_pct + "% / " +
                             root.structuralData.adaptive_infill.stress_zone_density_pct + "% — " +
                             (root.structuralData.adaptive_infill.pattern || "") +
                             "  |  Экономия vs 80%: " +
                             (root.structuralData.adaptive_infill.estimated_material_saving_vs_uniform_80pct || ""))
                          : ""
                    color:    textColor
                    font:     UM.Theme.getFont("small")
                    wrapMode: Text.WordWrap
                }

                // "Apply recommended settings" one-click button
                Button {
                    width:   parent.width
                    text:    "Применить рекомендованные настройки"
                    enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                    visible: root.structuralData.recommended_settings !== undefined
                    onClicked: {
                        if (!aiAssistantBridge || aiAssistantBridge.busy) return
                        var msg = "Примени рекомендованные настройки из структурного анализа."
                        addUserMessage(msg)
                        aiAssistantBridge.sendMessage(msg)
                        messageList.positionViewAtEnd()
                    }
                }
            }
        }

        // ============================================================== //
        // QUICK ACTION PRESETS
        // ============================================================== //
        RowLayout {
            Layout.fillWidth: true
            spacing: 4
            opacity: (aiAssistantBridge && !aiAssistantBridge.busy) ? 1.0 : 0.4
            Behavior on opacity { NumberAnimation { duration: 200 } }

            // "Прочность" button
            Button {
                Layout.fillWidth: true
                text:    "Прочность"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                font:    UM.Theme.getFont("small")
                onClicked: {
                    if (!aiAssistantBridge || aiAssistantBridge.busy) return
                    var msg = "Выполни структурный анализ первого объекта сцены и предложи оптимальную ориентацию и адаптивное заполнение для максимальной прочности при минимальном расходе пластика."
                    addUserMessage(msg)
                    aiAssistantBridge.sendMessage(msg)
                    messageList.positionViewAtEnd()
                }
            }

            // "Настройки" button
            Button {
                Layout.fillWidth: true
                text:    "Настройки"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                font:    UM.Theme.getFont("small")
                onClicked: {
                    if (!aiAssistantBridge || aiAssistantBridge.busy) return
                    var msg = "Прочитай текущие настройки и состояние сцены. Предложи конкретные улучшения для качества и скорости печати."
                    addUserMessage(msg)
                    aiAssistantBridge.sendMessage(msg)
                    messageList.positionViewAtEnd()
                }
            }

            // "Слайсинг" button
            Button {
                Layout.fillWidth: true
                text:    "Слайсинг"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                font:    UM.Theme.getFont("small")
                onClicked: {
                    if (!aiAssistantBridge || aiAssistantBridge.busy) return
                    var msg = "Запусти слайсинг текущей сцены."
                    addUserMessage(msg)
                    aiAssistantBridge.sendMessage(msg)
                    messageList.positionViewAtEnd()
                }
            }
        }

        // ============================================================== //
        // CHAT MESSAGE LIST
        // ============================================================== //
        Rectangle {
            Layout.fillWidth:  true
            Layout.fillHeight: true
            color:        "transparent"
            border.width: 1
            border.color: borderColor
            radius:       3

            ListView {
                id: messageList
                anchors.fill:    parent
                anchors.margins: 8
                model:   messages
                spacing: 8
                clip:    true

                delegate: Column {
                    width:   messageList.width
                    spacing: 2

                    // Sender label
                    Label {
                        anchors.right: (model.role === "user") ? parent.right : undefined
                        text:  (model.role === "user") ? "Вы" : "AI"
                        color: (model.role === "user") ? accentColor : mutedColor
                        font:  UM.Theme.getFont("small")
                    }

                    // Bubble
                    Rectangle {
                        id: bubble
                        anchors.right: (model.role === "user") ? parent.right : undefined
                        width:  Math.min(bubbleTxt.implicitWidth + 18,
                                         messageList.width * 0.88)
                        height: bubbleTxt.implicitHeight + 14
                        radius: 8
                        color:  model.isError
                                ? "#5c1a1a"
                                : (model.role === "user" ? accentColor : borderColor)

                        Label {
                            id: bubbleTxt
                            anchors {
                                left: parent.left; right: parent.right
                                top:  parent.top;  bottom: parent.bottom
                                margins: 8
                            }
                            text:     model.text
                            color:    model.isError
                                      ? "#ff8585"
                                      : (model.role === "user" ? "white" : textColor)
                            font:     UM.Theme.getFont("default")
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // Typing indicator footer
                footer: Item {
                    width:   messageList.width
                    height:  (aiAssistantBridge &&
                               aiAssistantBridge.busy &&
                               !aiAssistantBridge.confirmationPending) ? 28 : 0
                    visible: height > 0
                    Behavior on height { NumberAnimation { duration: 150 } }

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left:           parent.left
                        spacing: 5

                        Label {
                            text:  "AI  "
                            color: mutedColor
                            font:  UM.Theme.getFont("small")
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Repeater {
                            model: 3
                            delegate: Rectangle {
                                property int dotIndex: index
                                width: 7; height: 7; radius: 3.5
                                color: mutedColor
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: 0.2

                                SequentialAnimation on opacity {
                                    running: aiAssistantBridge && aiAssistantBridge.busy
                                    loops:   Animation.Infinite
                                    PauseAnimation  { duration: dotIndex * 200 }
                                    NumberAnimation { to: 1.0; duration: 300; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 0.2; duration: 300; easing.type: Easing.InOutSine }
                                    PauseAnimation  { duration: (2 - dotIndex) * 200 + 200 }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ============================================================== //
        // CONFIRMATION PANEL
        // ============================================================== //
        Rectangle {
            Layout.fillWidth: true
            visible:          aiAssistantBridge && aiAssistantBridge.confirmationPending
            color:            "transparent"
            border.width:     1
            border.color:     "#f39c12"
            radius:           4
            implicitHeight:   cfmCol.implicitHeight + 16

            ColumnLayout {
                id: cfmCol
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                spacing: 6

                Label {
                    Layout.fillWidth: true
                    text:  "Подтвердить действие"
                    color: "#f39c12"
                    font:  UM.Theme.getFont("default_bold")
                }

                Label {
                    Layout.fillWidth: true
                    text:     aiAssistantBridge
                              ? root.toolHumanName(aiAssistantBridge.confirmationTool) : ""
                    color:    textColor
                    font:     UM.Theme.getFont("default")
                    wrapMode: Text.WordWrap
                }

                Label {
                    Layout.fillWidth: true
                    text:             aiAssistantBridge ? aiAssistantBridge.confirmationArguments : ""
                    color:            mutedColor
                    font:             UM.Theme.getFont("small")
                    wrapMode:         Text.WordWrap
                    maximumLineCount: 6
                    elide:            Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Button {
                        Layout.fillWidth: true
                        text:    "Выполнить"
                        onClicked: aiAssistantBridge.confirmAction()
                    }
                    Button {
                        Layout.fillWidth: true
                        text:    "Отмена"
                        onClicked: aiAssistantBridge.cancelAction()
                    }
                }
            }
        }

        // ============================================================== //
        // INPUT ROW
        // ============================================================== //
        RowLayout {
            Layout.fillWidth: true
            spacing: UM.Theme.getSize("default_margin").width

            TextField {
                id:              messageInput
                Layout.fillWidth: true
                enabled:         aiAssistantBridge ? !aiAssistantBridge.busy : false
                placeholderText: "Например: кронштейн под нагрузку 50 кг..."
                selectByMouse:   true
                onAccepted:      sendBtn.clicked()
            }

            Button {
                id:      sendBtn
                text:    "→"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                onClicked: {
                    var txt = messageInput.text.trim()
                    if (!txt || !aiAssistantBridge || aiAssistantBridge.busy) return
                    addUserMessage(txt)
                    aiAssistantBridge.sendMessage(txt)
                    messageInput.clear()
                    messageList.positionViewAtEnd()
                }
            }
        }
    }
}
