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
    // Applied settings state
    // ------------------------------------------------------------------ //
    property var  appliedSettings:    ([])
    property bool hasApplied:         root.appliedSettings.length > 0
    property bool appliedExpanded:    true

    // Human-readable labels for slicer keys
    function settingLabel(key) {
        var m = {
            "printing_mode":              "Режим печати",
            "layer_height":               "Высота слоя (мм)",
            "layer_height_0":             "Высота 1-го слоя (мм)",
            "infill_sparse_density":      "Заполнение (%)",
            "infill_pattern":             "Паттерн заполнения",
            "wall_line_count":            "Количество стенок",
            "support_enable":             "Поддержки",
            "support_type":               "Тип поддержек",
            "material_print_temperature": "Температура (°C)",
            "print_speed":                "Скорость (мм/с)",
            "retraction_enable":          "Ретракция",
            "retraction_amount":          "Длина ретракции (мм)",
            "adhesion_type":              "Адгезия"
        }
        return m[key] || key
    }

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
            "scene.move_object":                 "Переместить объект",
            "scene.rotate_object":               "Повернуть объект",
            "settings.apply":                    "Применить настройки",
            "settings.apply_print_profile":      "Применить профиль печати",
            "backend.start_slicing":             "Запустить слайсинг",
            "export.scene":                      "Экспортировать сцену"
        }
        return m[n] || n
    }

    // ------------------------------------------------------------------ //
    // Print mode recommendation state
    // ------------------------------------------------------------------ //
    property var  printModeData:    ({})
    property bool hasPrintMode:     Object.keys(root.printModeData).length > 0
    property bool printModeExpanded: true

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
        onPrintModeReady: {
            try {
                root.printModeData    = JSON.parse(aiAssistantBridge.lastPrintModeResult)
                root.printModeExpanded = true
            } catch(e) {
                root.printModeData = {}
            }
        }
        onSettingsApplied: {
            try {
                root.appliedSettings = JSON.parse(aiAssistantBridge.lastAppliedSettings)
                root.appliedExpanded = true
            } catch(e) {
                root.appliedSettings = []
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
        // PRINT MODE & MATERIAL RECOMMENDATION CARD
        // ============================================================== //
        Rectangle {
            Layout.fillWidth: true
            visible:          root.hasPrintMode
            color:            "transparent"
            border.width:     1
            border.color:     root.printModeData.recommended_mode === "5D" ? "#9b59b6" : "#2980b9"
            radius:           4
            implicitHeight:   pmHeader.implicitHeight + 16 +
                              (root.printModeExpanded ? pmBody.implicitHeight + 8 : 0)

            Behavior on implicitHeight { NumberAnimation { duration: 150 } }

            RowLayout {
                id: pmHeader
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                spacing: 6

                Label {
                    Layout.fillWidth: true
                    text:  "Режим и материал"
                    color: root.printModeData.recommended_mode === "5D" ? "#9b59b6" : "#2980b9"
                    font:  UM.Theme.getFont("default_bold")
                }

                // Mode badge
                Rectangle {
                    color:  root.printModeData.recommended_mode === "5D" ? "#9b59b6" : "#2980b9"
                    radius: 3
                    width:  modeBadgeLbl.implicitWidth + 10
                    height: modeBadgeLbl.implicitHeight + 4
                    Label {
                        id: modeBadgeLbl
                        anchors.centerIn: parent
                        text:  root.printModeData.recommended_mode || "3D"
                        color: "white"
                        font:  UM.Theme.getFont("small")
                    }
                }

                // Material badge
                Rectangle {
                    visible: root.printModeData.recommended_material !== undefined
                    color:   "#16a085"
                    radius:  3
                    width:   matBadgeLbl.implicitWidth + 10
                    height:  matBadgeLbl.implicitHeight + 4
                    Label {
                        id: matBadgeLbl
                        anchors.centerIn: parent
                        text:  root.printModeData.recommended_material || ""
                        color: "white"
                        font:  UM.Theme.getFont("small")
                    }
                }

                Label {
                    text:  root.printModeExpanded ? "▲" : "▼"
                    color: root.printModeData.recommended_mode === "5D" ? "#9b59b6" : "#2980b9"
                    font:  UM.Theme.getFont("small")
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.printModeExpanded = !root.printModeExpanded
                    }
                }
            }

            Column {
                id: pmBody
                anchors { left: parent.left; right: parent.right; top: pmHeader.bottom; margins: 8 }
                spacing: 5
                visible: root.printModeExpanded
                opacity: root.printModeExpanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }

                // Beginner summary — the most important line
                Label {
                    width:    parent.width
                    text:     root.printModeData.beginner_summary || ""
                    color:    textColor
                    font:     UM.Theme.getFont("default")
                    wrapMode: Text.WordWrap
                }

                // Divider
                Rectangle { width: parent.width; height: 1; color: borderColor }

                // Dimensions + estimated mass row
                RowLayout {
                    width: parent.width
                    spacing: 8

                    Label {
                        text: {
                            var d = root.printModeData.dimensions_mm
                            if (!d) return ""
                            return d.x.toFixed(0) + " x " + d.z.toFixed(0) + " x " + d.y.toFixed(0) + " мм"
                        }
                        color: mutedColor
                        font:  UM.Theme.getFont("small")
                    }

                    Label {
                        Layout.fillWidth: true
                        text: {
                            var m = root.printModeData.estimated_mass_g
                            var mat = root.printModeData.recommended_material
                            if (!m || !mat) return ""
                            return "~" + m[mat].toFixed(0) + " г (" + mat + ")"
                        }
                        color: mutedColor
                        font:  UM.Theme.getFont("small")
                        horizontalAlignment: Text.AlignRight
                    }
                }

                // Material reason
                Label {
                    width:    parent.width
                    visible:  root.printModeData.material_reason !== undefined
                    text:     root.printModeData.material_reason || ""
                    color:    mutedColor
                    font:     UM.Theme.getFont("small")
                    wrapMode: Text.WordWrap
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
        // APPLIED SETTINGS CARD
        // ============================================================== //
        Rectangle {
            Layout.fillWidth: true
            visible:          root.hasApplied
            color:            "transparent"
            border.width:     1
            border.color:     "#27ae60"
            radius:           4
            implicitHeight:   appliedHeader.implicitHeight + 16 +
                              (root.appliedExpanded ? appliedBody.implicitHeight + 8 : 0)

            Behavior on implicitHeight { NumberAnimation { duration: 150 } }

            RowLayout {
                id: appliedHeader
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                spacing: 6

                Label {
                    Layout.fillWidth: true
                    text:  "Настройки применены"
                    color: "#27ae60"
                    font:  UM.Theme.getFont("default_bold")
                }

                Rectangle {
                    color:  "#27ae60"
                    radius: 3
                    width:  appliedCountLabel.implicitWidth + 10
                    height: appliedCountLabel.implicitHeight + 4
                    Label {
                        id: appliedCountLabel
                        anchors.centerIn: parent
                        text:  root.appliedSettings.length + " параметров"
                        color: "white"
                        font:  UM.Theme.getFont("small")
                    }
                }

                Label {
                    text:  root.appliedExpanded ? "▲" : "▼"
                    color: "#27ae60"
                    font:  UM.Theme.getFont("small")
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.appliedExpanded = !root.appliedExpanded
                    }
                }
            }

            Column {
                id: appliedBody
                anchors {
                    left: parent.left; right: parent.right
                    top:  appliedHeader.bottom; margins: 8
                }
                spacing: 4
                visible: root.appliedExpanded
                opacity: root.appliedExpanded ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }

                Repeater {
                    model: root.appliedSettings
                    delegate: RowLayout {
                        width: appliedBody.width
                        spacing: 8

                        Label {
                            Layout.fillWidth: true
                            text:     root.settingLabel(modelData.key || "")
                            color:    mutedColor
                            font:     UM.Theme.getFont("small")
                        }

                        Label {
                            text:  {
                                var v = modelData.value
                                if (v === true)  return "вкл"
                                if (v === false) return "выкл"
                                return String(v)
                            }
                            color: "#27ae60"
                            font:  UM.Theme.getFont("small")
                        }
                    }
                }
            }
        }

        // ============================================================== //
        // BIG ONE-CLICK BUTTON
        // ============================================================== //
        Button {
            Layout.fillWidth: true
            enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
            text:    aiAssistantBridge && aiAssistantBridge.busy
                     ? "Идёт настройка..."
                     : "Настроить и начать слайсинг"
            height:  44

            background: Rectangle {
                color:  (parent.enabled && !parent.pressed)
                        ? (aiAssistantBridge && aiAssistantBridge.busy ? "#7f8c8d" : "#27ae60")
                        : "#1e8449"
                radius: 5
                Behavior on color { ColorAnimation { duration: 150 } }
            }

            contentItem: Label {
                text:              parent.text
                color:             "white"
                font.bold:         true
                font.pixelSize:    14
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment:   Text.AlignVCenter
            }

            onClicked: {
                if (!aiAssistantBridge || aiAssistantBridge.busy) return
                addUserMessage("Настроить и начать слайсинг автоматически")
                aiAssistantBridge.triggerFullSetup()
                messageList.positionViewAtEnd()
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

            Button {
                Layout.fillWidth: true
                text:    "Прочность"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                font:    UM.Theme.getFont("small")
                onClicked: {
                    if (!aiAssistantBridge || aiAssistantBridge.busy) return
                    var msg = "Выполни структурный анализ первого объекта и предложи оптимальные настройки для максимальной прочности."
                    addUserMessage(msg)
                    aiAssistantBridge.sendMessage(msg)
                    messageList.positionViewAtEnd()
                }
            }

            Button {
                Layout.fillWidth: true
                text:    "Настройки"
                enabled: aiAssistantBridge ? !aiAssistantBridge.busy : false
                font:    UM.Theme.getFont("small")
                onClicked: {
                    if (!aiAssistantBridge || aiAssistantBridge.busy) return
                    var msg = "Прочитай текущие настройки и предложи улучшения для качества и скорости печати."
                    addUserMessage(msg)
                    aiAssistantBridge.sendMessage(msg)
                    messageList.positionViewAtEnd()
                }
            }

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
