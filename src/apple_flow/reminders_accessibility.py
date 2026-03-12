"""Accessibility-backed fallback for Reminders grouped and nested lists."""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
from collections import defaultdict
from typing import Any

from .osascript_utils import run_osascript_with_recovery
from . import reminders_runtime_gate

logger = logging.getLogger("apple_flow.reminders_accessibility")

AX_REMINDER_ID_PREFIX = "ax://"
_SIDEBAR_OUTLINE_SPEC = 'outline 1 of scroll area 1 of UI element 1 of splitter group 1 of front window'
_DETAIL_OUTLINE_SPEC = 'outline 1 of scroll area 1 of UI element 3 of splitter group 1 of front window'

_SWIFT_HELPER = r'''
import Cocoa
import ApplicationServices
import Foundation

typealias JSONObject = [String: Any]

func stdinJSON() -> JSONObject {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard !data.isEmpty else { return [:] }
    guard let raw = try? JSONSerialization.jsonObject(with: data) as? JSONObject else { return [:] }
    return raw
}

func stdoutJSON(_ payload: JSONObject) {
    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
        print("{\"error\":\"json encode failed\",\"ok\":false}")
        return
    }
    FileHandle.standardOutput.write(data)
}

func attr(_ element: AXUIElement, _ name: String) -> AnyObject? {
    var value: CFTypeRef?
    let err = AXUIElementCopyAttributeValue(element, name as CFString, &value)
    return err == .success ? (value as AnyObject?) : nil
}

func children(_ element: AXUIElement) -> [AXUIElement] {
    (attr(element, kAXChildrenAttribute as String) as? [AXUIElement]) ?? []
}

func stringValue(_ value: AnyObject?) -> String {
    if let string = value as? String { return string }
    if let number = value as? NSNumber { return number.stringValue }
    return ""
}

func boolValue(_ value: AnyObject?) -> Bool {
    if let number = value as? NSNumber { return number.boolValue }
    return false
}

func intValue(_ value: AnyObject?) -> Int {
    if let number = value as? NSNumber { return number.intValue }
    return -1
}

func stringAttr(_ element: AXUIElement, _ name: String) -> String {
    stringValue(attr(element, name))
}

func boolAttr(_ element: AXUIElement, _ name: String) -> Bool {
    boolValue(attr(element, name))
}

func intAttr(_ element: AXUIElement, _ name: String) -> Int {
    intValue(attr(element, name))
}

func descendants(_ element: AXUIElement, role: String? = nil, desc: String? = nil) -> [AXUIElement] {
    var results: [AXUIElement] = []
    func walk(_ current: AXUIElement) {
        let roleValue = stringAttr(current, kAXRoleAttribute as String)
        let descValue = stringAttr(current, kAXDescriptionAttribute as String)
        if (role == nil || roleValue == role!) && (desc == nil || descValue == desc!) {
            results.append(current)
        }
        for child in children(current) {
            walk(child)
        }
    }
    walk(element)
    return results
}

func firstDescendant(_ element: AXUIElement, role: String? = nil, desc: String? = nil) -> AXUIElement? {
    descendants(element, role: role, desc: desc).first
}

func perform(_ element: AXUIElement, action: String) -> Bool {
    AXUIElementPerformAction(element, action as CFString) == .success
}

func setString(_ element: AXUIElement, _ name: String, value: String) -> Bool {
    AXUIElementSetAttributeValue(element, name as CFString, value as CFTypeRef) == .success
}

func setBool(_ element: AXUIElement, _ name: String, value: Bool) -> Bool {
    AXUIElementSetAttributeValue(element, name as CFString, value as CFTypeRef) == .success
}

func sleepSmall(_ seconds: Double = 0.15) {
    Thread.sleep(forTimeInterval: seconds)
}

func waitUntil(timeout: Double, _ predicate: () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if predicate() { return true }
        sleepSmall(0.1)
    }
    return predicate()
}

func remindersApp() -> (NSRunningApplication, AXUIElement)? {
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    guard AXIsProcessTrustedWithOptions(options) else { return nil }
    guard let app = NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.reminders").first else {
        return nil
    }
    app.activate(options: [.activateIgnoringOtherApps])
    sleepSmall(0.2)
    return (app, AXUIElementCreateApplication(app.processIdentifier))
}

func mainWindow(_ appElement: AXUIElement) -> AXUIElement? {
    (attr(appElement, kAXWindowsAttribute as String) as? [AXUIElement])?.first
}

func splitGroup(_ appElement: AXUIElement) -> AXUIElement? {
    guard let window = mainWindow(appElement) else { return nil }
    return firstDescendant(window, role: "AXSplitGroup")
}

func sidebarOutline(_ appElement: AXUIElement) -> AXUIElement? {
    guard let split = splitGroup(appElement) else { return nil }
    if let direct = firstDescendant(split, role: "AXOutline", desc: "Account Lists") {
        return direct
    }
    if let sidebar = children(split).first(where: {
        stringAttr($0, kAXRoleAttribute as String) == "AXLayoutArea"
            && stringAttr($0, kAXDescriptionAttribute as String) == "Reminder lists"
    }) {
        return firstDescendant(sidebar, role: "AXOutline") ?? firstDescendant(sidebar)
    }
    return firstDescendant(split, role: "AXOutline") ?? firstDescendant(split)
}

func detailLayout(_ appElement: AXUIElement, selectedName: String) -> AXUIElement? {
    guard let split = splitGroup(appElement) else { return nil }
    return children(split).first(where: {
        stringAttr($0, kAXRoleAttribute as String) == "AXLayoutArea"
            && stringAttr($0, kAXDescriptionAttribute as String) == selectedName
    })
}

func detailOutline(_ appElement: AXUIElement, selectedName: String) -> AXUIElement? {
    guard let layout = detailLayout(appElement, selectedName: selectedName) else { return nil }
    return firstDescendant(layout, role: "AXOutline")
}

func primaryRowText(_ row: AXUIElement) -> String {
    for element in descendants(row, role: "AXTextField") + descendants(row, role: "AXStaticText") {
        let value = stringAttr(element, kAXValueAttribute as String).trimmingCharacters(in: .whitespacesAndNewlines)
        if !value.isEmpty { return value }
    }
    return ""
}

func cellDescription(_ row: AXUIElement) -> String {
    if let cell = children(row).first {
        let desc = stringAttr(cell, kAXDescriptionAttribute as String)
        if !desc.isEmpty { return desc }
    }
    return stringAttr(row, kAXDescriptionAttribute as String)
}

func rowHasDisclosure(_ row: AXUIElement) -> Bool {
    !descendants(row, role: "AXDisclosureTriangle").isEmpty
}

func parseListName(cellDescription: String, fallback: String) -> String {
    let trimmedFallback = fallback.trimmingCharacters(in: .whitespacesAndNewlines)
    if !trimmedFallback.isEmpty && trimmedFallback != "My Lists" {
        return trimmedFallback
    }
    let firstPart = cellDescription.split(separator: ",", maxSplits: 1).first.map(String.init)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if firstPart == "My Lists" || firstPart.hasPrefix("Suggested List:") {
        return ""
    }
    return firstPart
}

func pathJoin(_ segments: [String]) -> String {
    segments.filter { !$0.isEmpty }.joined(separator: "/")
}

func sidebarEntries(_ outline: AXUIElement, defaultAccount: String, includeGroups: Bool = false) -> [(AXUIElement, [String: Any])] {
    let rows = (attr(outline, kAXRowsAttribute as String) as? [AXUIElement]) ?? []
    var groupStack: [Int: String] = [:]
    var lists: [(AXUIElement, [String: Any])] = []

    for row in rows {
        let level = max(0, intAttr(row, kAXDisclosureLevelAttribute as String))
        let text = primaryRowText(row)
        let desc = cellDescription(row)
        let hasDisclosure = rowHasDisclosure(row)

        if hasDisclosure && !text.isEmpty {
            groupStack = groupStack.filter { $0.key < level }
            groupStack[level] = text
            if includeGroups {
                let parentSegments = groupStack
                    .filter { $0.key < level }
                    .sorted { $0.key < $1.key }
                    .map(\.value)
                let segments = ([defaultAccount] + parentSegments + [text]).filter { !$0.isEmpty }
                let parentSegmentsOnly = ([defaultAccount] + parentSegments).filter { !$0.isEmpty }
                lists.append(
                    (row, [
                        "id": "",
                        "name": text,
                        "path": pathJoin(segments),
                        "account": defaultAccount,
                        "account_id": "",
                        "parent_id": "",
                        "parent_path": pathJoin(parentSegmentsOnly),
                        "is_top_level": parentSegments.isEmpty,
                        "source": "accessibility",
                        "kind": "group",
                    ])
                )
            }
            continue
        }

        let listName = parseListName(cellDescription: desc, fallback: text)
        if listName.isEmpty {
            continue
        }

        let parentSegments = groupStack
            .filter { $0.key < level }
            .sorted { $0.key < $1.key }
            .map(\.value)
        let segments = ([defaultAccount] + parentSegments + [listName]).filter { !$0.isEmpty }
        let parentSegmentsOnly = ([defaultAccount] + parentSegments).filter { !$0.isEmpty }
        lists.append(
            (row, [
                "id": "",
                "name": listName,
                "path": pathJoin(segments),
                "account": defaultAccount,
                "account_id": "",
                "parent_id": "",
                "parent_path": pathJoin(parentSegmentsOnly),
                "is_top_level": parentSegments.isEmpty,
                "source": "accessibility",
                "kind": "list",
            ])
        )
    }

    return lists
}

func sidebarCatalog(_ outline: AXUIElement, defaultAccount: String, includeGroups: Bool = false) -> [[String: Any]] {
    sidebarEntries(outline, defaultAccount: defaultAccount, includeGroups: includeGroups).map(\.1)
}

@discardableResult
func selectSidebarEntry(_ appElement: AXUIElement, path: String, defaultAccount: String, includeGroups: Bool = false) -> String? {
    guard let outline = sidebarOutline(appElement) else { return nil }
    let entries = sidebarEntries(outline, defaultAccount: defaultAccount, includeGroups: includeGroups)
    for (row, entry) in entries {
        guard (entry["path"] as? String) == path else { continue }
        if !perform(row, action: kAXPressAction as String) {
            if let cell = children(row).first {
                _ = perform(cell, action: kAXPressAction as String)
            }
            _ = setBool(row, kAXSelectedAttribute as String, value: true)
        }
        sleepSmall(0.25)
        return entry["name"] as? String
    }
    return nil
}

@discardableResult
func selectList(_ appElement: AXUIElement, path: String, defaultAccount: String) -> String? {
    selectSidebarEntry(appElement, path: path, defaultAccount: defaultAccount)
}

struct ReminderRow {
    let row: AXUIElement
    let checkbox: AXUIElement
    let titleField: AXUIElement
    let bodyField: AXUIElement?
    let name: String
    let body: String
    let completed: Bool
    let sectionName: String
}

func reminderRowDetails(_ row: AXUIElement, sectionName: String, includeEmpty: Bool = false) -> ReminderRow? {
    guard
        let group = descendants(row, role: "AXGroup").first,
        let checkbox = descendants(group, role: "AXCheckBox").first
    else {
        return nil
    }
    let textFields = descendants(group, role: "AXTextField")
    guard let titleField = textFields.first else { return nil }
    let title = stringAttr(titleField, kAXValueAttribute as String).trimmingCharacters(in: .whitespacesAndNewlines)
    if title.isEmpty && !includeEmpty { return nil }
    let bodyField = textFields.dropFirst().first
    let body = bodyField.map { stringAttr($0, kAXValueAttribute as String) } ?? ""
    return ReminderRow(
        row: row,
        checkbox: checkbox,
        titleField: titleField,
        bodyField: bodyField,
        name: title,
        body: body,
        completed: boolAttr(checkbox, kAXValueAttribute as String),
        sectionName: sectionName,
    )
}

func normalizedText(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
}

func sectionHeaderName(_ row: AXUIElement) -> String? {
    guard descendants(row, role: "AXGroup").isEmpty else { return nil }
    let desc = cellDescription(row)
    if desc.contains("Completed, Hiding completed reminders") {
        return nil
    }
    let text = primaryRowText(row).trimmingCharacters(in: .whitespacesAndNewlines)
    if text.isEmpty || normalizedText(text).hasSuffix("completed") {
        return nil
    }
    return text
}

func placeholderSectionName(_ row: AXUIElement) -> String? {
    let desc = cellDescription(row).trimmingCharacters(in: .whitespacesAndNewlines)
    let prefix = "New reminder in "
    guard desc.hasPrefix(prefix) else { return nil }
    return String(desc.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
}

func reminderRows(_ outline: AXUIElement, includeEmpty: Bool = false) -> [ReminderRow] {
    let rows = (attr(outline, kAXRowsAttribute as String) as? [AXUIElement]) ?? []
    var items: [ReminderRow] = []
    var currentSection = ""

    for row in rows {
        if let sectionName = sectionHeaderName(row) {
            currentSection = sectionName
            continue
        }
        if let placeholderSection = placeholderSectionName(row) {
            currentSection = placeholderSection
            if let item = reminderRowDetails(row, sectionName: currentSection, includeEmpty: includeEmpty) {
                items.append(item)
            }
            continue
        }
        if let item = reminderRowDetails(row, sectionName: currentSection, includeEmpty: includeEmpty) {
            items.append(item)
        }
    }

    return items
}

func sectionNames(_ outline: AXUIElement) -> [String] {
    let rows = (attr(outline, kAXRowsAttribute as String) as? [AXUIElement]) ?? []
    var names: [String] = []
    for row in rows {
        if let sectionName = sectionHeaderName(row), !names.contains(sectionName) {
            names.append(sectionName)
        }
        if let sectionName = placeholderSectionName(row), !names.contains(sectionName) {
            names.append(sectionName)
        }
    }
    return names
}

func matchingRow(_ items: [ReminderRow], spec: JSONObject) -> ReminderRow? {
    let name = (spec["name"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let ordinal = max(1, spec["ordinal"] as? Int ?? 1)
    let bodyPrefix = (spec["body_prefix"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let sectionName = normalizedText(spec["section_name"] as? String ?? "")
    let candidates = items.filter {
        $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == name
            && (sectionName.isEmpty || normalizedText($0.sectionName) == sectionName)
    }
    if candidates.isEmpty { return nil }
    if !bodyPrefix.isEmpty {
        let narrowed = candidates.filter { $0.body.lowercased().hasPrefix(bodyPrefix) }
        if !narrowed.isEmpty {
            return narrowed[min(max(0, ordinal - 1), narrowed.count - 1)]
        }
    }
    return candidates[min(max(0, ordinal - 1), candidates.count - 1)]
}

func setReminderBody(_ row: ReminderRow, note: String) -> Bool {
    guard let bodyField = row.bodyField else { return false }
    let existing = row.body.trimmingCharacters(in: .whitespacesAndNewlines)
    let combined = existing.isEmpty ? note : existing + "\n\n" + note
    guard setString(bodyField, kAXValueAttribute as String, value: combined) else { return false }
    _ = perform(bodyField, action: kAXConfirmAction as String)
    return true
}

func addReminder(in appElement: AXUIElement, triggerStrategy: String = "") -> Bool {
    let useMenuOnly = normalizedText(triggerStrategy) == "menu"
    if !useMenuOnly {
        if let button = descendants(appElement, role: "AXButton").first(where: {
            let desc = stringAttr($0, kAXDescriptionAttribute as String)
            return desc == "Add Reminder" || desc == "New Reminder"
        }) {
            return perform(button, action: kAXPressAction as String)
        }
    }
    guard let fileItem = menuBarItem(appElement, title: "File") else { return false }
    _ = perform(fileItem, action: kAXPressAction as String)
    sleepSmall(0.1)
    guard let newReminderItem = submenuItems(fileItem).first(where: {
        normalizedText(stringAttr($0, kAXTitleAttribute as String)) == "new reminder"
    }) else {
        return false
    }
    return perform(newReminderItem, action: kAXPressAction as String)
}

func selectRow(_ row: AXUIElement) {
    _ = setBool(row, kAXSelectedAttribute as String, value: true)
    sleepSmall(0.2)
}

func sectionAnchorRow(_ outline: AXUIElement, sectionName: String) -> AXUIElement? {
    let target = normalizedText(sectionName)
    guard !target.isEmpty else { return nil }
    let rows = (attr(outline, kAXRowsAttribute as String) as? [AXUIElement]) ?? []
    for row in rows {
        if let placeholder = placeholderSectionName(row), normalizedText(placeholder) == target {
            return row
        }
    }
    return nil
}

func menuBarItem(_ appElement: AXUIElement, title: String) -> AXUIElement? {
    guard let menuBar = firstDescendant(appElement, role: "AXMenuBar") else { return nil }
    return children(menuBar).first { stringAttr($0, kAXTitleAttribute as String) == title }
}

func menuItem(_ appElement: AXUIElement, menuTitle: String, itemTitle: String) -> AXUIElement? {
    guard let topItem = menuBarItem(appElement, title: menuTitle) else { return nil }
    _ = perform(topItem, action: kAXPressAction as String)
    sleepSmall(0.1)
    return submenuItems(topItem).first {
        normalizedText(stringAttr($0, kAXTitleAttribute as String)) == normalizedText(itemTitle)
    }
}

func submenuItems(_ menuItem: AXUIElement) -> [AXUIElement] {
    for child in children(menuItem) where stringAttr(child, kAXRoleAttribute as String) == "AXMenu" {
        return children(child).filter { stringAttr($0, kAXRoleAttribute as String) == "AXMenuItem" }
    }
    return []
}

func moveReminderToSection(appElement: AXUIElement, row: AXUIElement, targetSectionName: String) -> Bool {
    selectRow(row)
    guard let fileItem = menuBarItem(appElement, title: "File") else { return false }
    let moveItems = submenuItems(fileItem)
    guard let moveItem = moveItems.first(where: {
        normalizedText(stringAttr($0, kAXTitleAttribute as String)).contains("move to section")
    }) else {
        return false
    }
    let targets = submenuItems(moveItem)
    guard let target = targets.first(where: {
        normalizedText(stringAttr($0, kAXTitleAttribute as String)) == normalizedText(targetSectionName)
    }) else {
        return false
    }
    return perform(target, action: kAXPressAction as String)
}

func applyListName(_ root: AXUIElement, listName: String) -> Bool {
    let fields = descendants(root, role: "AXTextField")
    for field in fields {
        if setString(field, kAXValueAttribute as String, value: listName) {
            _ = perform(field, action: kAXConfirmAction as String)
            return true
        }
    }
    return false
}

func triggerContextNewList(_ appElement: AXUIElement, row: AXUIElement) -> Bool {
    if !perform(row, action: "AXShowMenu"), let cell = children(row).first {
        _ = perform(cell, action: "AXShowMenu")
    }
    sleepSmall(0.15)
    if let item = descendants(appElement, role: "AXMenuItem").first(where: {
        normalizedText(stringAttr($0, kAXTitleAttribute as String)) == "new list"
    }) {
        return perform(item, action: kAXPressAction as String)
    }
    return false
}

func rowMenuTitles(appElement: AXUIElement, defaultAccount: String, path: String) -> [String] {
    guard let outline = sidebarOutline(appElement) else { return [] }
    let entries = sidebarEntries(outline, defaultAccount: defaultAccount, includeGroups: true)
    guard let row = entries.first(where: { ($0.1["path"] as? String) == path })?.0 else { return [] }
    if !perform(row, action: "AXShowMenu"), let cell = children(row).first {
        _ = perform(cell, action: "AXShowMenu")
    }
    sleepSmall(0.2)
    var titles: [String] = []
    for item in descendants(appElement, role: "AXMenuItem") {
        let title = stringAttr(item, kAXTitleAttribute as String).trimmingCharacters(in: .whitespacesAndNewlines)
        if !title.isEmpty && !titles.contains(title) {
            titles.append(title)
        }
    }
    return titles
}

func createGroup(appElement: AXUIElement, defaultAccount: String, groupName: String) -> JSONObject {
    guard let outline = sidebarOutline(appElement) else {
        return ["ok": false, "error": "sidebar not found"]
    }
    let groupPath = pathJoin(([defaultAccount, groupName]).filter { !$0.isEmpty })
    if sidebarEntries(outline, defaultAccount: defaultAccount, includeGroups: true).contains(where: {
        ($0.1["path"] as? String) == groupPath && ($0.1["kind"] as? String) == "group"
    }) {
        return ["ok": true, "status": "exists", "path": groupPath]
    }
    guard let newGroupItem = menuItem(appElement, menuTitle: "File", itemTitle: "New Group") else {
        return ["ok": false, "error": "new group menu item not found"]
    }
    guard perform(newGroupItem, action: kAXPressAction as String) else {
        return ["ok": false, "error": "unable to trigger new group"]
    }
    sleepSmall(0.1)
    guard let focusedValue = attr(appElement, kAXFocusedUIElementAttribute as String) else {
        return ["ok": false, "error": "group title field not focused"]
    }
    let focused = focusedValue as! AXUIElement
    guard setString(focused, kAXValueAttribute as String, value: groupName) else {
        return ["ok": false, "error": "unable to set group name"]
    }
    _ = perform(focused, action: kAXConfirmAction as String)
    let created = waitUntil(timeout: 5.0) {
        guard let currentOutline = sidebarOutline(appElement) else { return false }
        return sidebarEntries(currentOutline, defaultAccount: defaultAccount, includeGroups: true).contains {
            ($0.1["path"] as? String) == groupPath && ($0.1["kind"] as? String) == "group"
        }
    }
    return created ? ["ok": true, "status": "created", "path": groupPath] : ["ok": false, "error": "group did not appear"]
}

func createList(appElement: AXUIElement, defaultAccount: String, parentPath: String, listName: String) -> JSONObject {
    guard let outline = sidebarOutline(appElement) else {
        return ["ok": false, "error": "sidebar not found"]
    }
    let listPath = pathJoin(([parentPath, listName]).filter { !$0.isEmpty })
    if sidebarEntries(outline, defaultAccount: defaultAccount).contains(where: { ($0.1["path"] as? String) == listPath }) {
        return ["ok": true, "status": "exists", "path": listPath]
    }
    let entries = sidebarEntries(outline, defaultAccount: defaultAccount, includeGroups: true)
    guard let groupRow = entries.first(where: { ($0.1["path"] as? String) == parentPath && ($0.1["kind"] as? String) == "group" })?.0 else {
        return ["ok": false, "error": "parent group not found"]
    }

    _ = selectSidebarEntry(appElement, path: parentPath, defaultAccount: defaultAccount, includeGroups: true)
    let triggeredViaContext = triggerContextNewList(appElement, row: groupRow)
    if !triggeredViaContext {
        guard let newListItem = menuItem(appElement, menuTitle: "File", itemTitle: "New List") else {
            return ["ok": false, "error": "new list menu item not found"]
        }
        guard perform(newListItem, action: kAXPressAction as String) else {
            return ["ok": false, "error": "unable to trigger new list"]
        }
    }
    sleepSmall(0.2)
    if let window = mainWindow(appElement),
       let sheet = (attr(window, "AXSheets") as? [AXUIElement])?.first {
        guard applyListName(sheet, listName: listName) else {
            return ["ok": false, "error": "unable to set list name"]
        }
        if let okButton = descendants(sheet, role: "AXButton").first(where: {
            normalizedText(stringAttr($0, kAXTitleAttribute as String)) == "ok"
        }) {
            _ = perform(okButton, action: kAXPressAction as String)
        }
    } else {
        guard let focusedValue = attr(appElement, kAXFocusedUIElementAttribute as String) else {
            return ["ok": false, "error": "list title field not focused"]
        }
        let focused = focusedValue as! AXUIElement
        if !setString(focused, kAXValueAttribute as String, value: listName) {
            guard let window = mainWindow(appElement), applyListName(window, listName: listName) else {
                return ["ok": false, "error": "unable to set list name"]
            }
        } else {
            _ = perform(focused, action: kAXConfirmAction as String)
        }
    }
    let created = waitUntil(timeout: 5.0) {
        guard let currentOutline = sidebarOutline(appElement) else { return false }
        return sidebarEntries(currentOutline, defaultAccount: defaultAccount).contains {
            ($0.1["path"] as? String) == listPath
        }
    }
    return created ? ["ok": true, "status": "created", "path": listPath] : ["ok": false, "error": "list did not appear"]
}

func createSection(appElement: AXUIElement, listPath: String, defaultAccount: String, sectionName: String) -> JSONObject {
    let cleanSectionName = sectionName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !cleanSectionName.isEmpty else {
        return ["ok": false, "error": "section name is required"]
    }
    guard let selectedName = selectList(appElement, path: listPath, defaultAccount: defaultAccount) else {
        return ["ok": false, "error": "list not found"]
    }
    guard let outline = detailOutline(appElement, selectedName: selectedName) else {
        return ["ok": false, "error": "detail list not found"]
    }
    if sectionNames(outline).contains(where: { normalizedText($0) == normalizedText(cleanSectionName) }) {
        return ["ok": true, "status": "exists", "section_name": cleanSectionName]
    }
    guard let newSectionItem = menuItem(appElement, menuTitle: "File", itemTitle: "New Section") else {
        return ["ok": false, "error": "new section menu item not found"]
    }
    guard perform(newSectionItem, action: kAXPressAction as String) else {
        return ["ok": false, "error": "unable to trigger new section"]
    }
    sleepSmall(0.15)
    guard let focusedValue = attr(appElement, kAXFocusedUIElementAttribute as String) else {
        return ["ok": false, "error": "section title field not focused"]
    }
    let focused = focusedValue as! AXUIElement
    guard setString(focused, kAXValueAttribute as String, value: cleanSectionName) else {
        return ["ok": false, "error": "unable to set section name"]
    }
    _ = perform(focused, action: kAXConfirmAction as String)
    let created = waitUntil(timeout: 5.0) {
        guard let currentOutline = detailOutline(appElement, selectedName: selectedName) else { return false }
        return sectionNames(currentOutline).contains(where: { normalizedText($0) == normalizedText(cleanSectionName) })
    }
    return created ? ["ok": true, "status": "created", "section_name": cleanSectionName] : ["ok": false, "error": "section did not appear"]
}

func createReminder(appElement: AXUIElement, listPath: String, defaultAccount: String, name: String, note: String, sectionName: String, triggerStrategy: String) -> JSONObject {
    guard let selectedName = selectList(appElement, path: listPath, defaultAccount: defaultAccount) else {
        return ["ok": false, "error": "list not found"]
    }
    guard let outline = detailOutline(appElement, selectedName: selectedName) else {
        return ["ok": false, "error": "detail list not found"]
    }
    if let anchor = sectionAnchorRow(outline, sectionName: sectionName) {
        selectRow(anchor)
    }
    let before = reminderRows(outline, includeEmpty: true)
    if let existingEmptyRow = before.first(where: {
        $0.name.isEmpty
            && (sectionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || normalizedText($0.sectionName) == normalizedText(sectionName))
    }) {
        guard setString(existingEmptyRow.titleField, kAXValueAttribute as String, value: name) else {
            return ["ok": false, "error": "unable to set reminder title"]
        }
        _ = perform(existingEmptyRow.titleField, action: kAXConfirmAction as String)
        if !note.isEmpty, let bodyField = existingEmptyRow.bodyField {
            _ = setString(bodyField, kAXValueAttribute as String, value: note)
            _ = perform(bodyField, action: kAXConfirmAction as String)
        }
        sleepSmall(0.2)
        return ["ok": true]
    }
    guard addReminder(in: appElement, triggerStrategy: triggerStrategy) else {
        return ["ok": false, "error": "unable to trigger new reminder"]
    }

    let created = waitUntil(timeout: 3.0) {
        guard let currentOutline = detailOutline(appElement, selectedName: selectedName) else { return false }
        return reminderRows(currentOutline, includeEmpty: true).count > before.count
    }
    guard created, let currentOutline = detailOutline(appElement, selectedName: selectedName) else {
        return ["ok": false, "error": "new reminder row did not appear"]
    }

    let candidates = reminderRows(currentOutline, includeEmpty: true).filter {
        sectionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || normalizedText($0.sectionName) == normalizedText(sectionName)
    }
    guard let row = candidates.first(where: { $0.name.isEmpty }) ?? candidates.first(where: { !$0.completed && $0.name == name }) ?? candidates.last else {
        return ["ok": false, "error": "unable to locate new reminder row"]
    }
    guard setString(row.titleField, kAXValueAttribute as String, value: name) else {
        return ["ok": false, "error": "unable to set reminder title"]
    }
    _ = perform(row.titleField, action: kAXConfirmAction as String)
    if !note.isEmpty, let bodyField = row.bodyField {
        _ = setString(bodyField, kAXValueAttribute as String, value: note)
        _ = perform(bodyField, action: kAXConfirmAction as String)
    }
    sleepSmall(0.2)
    return ["ok": true]
}

let input = stdinJSON()
let action = input["action"] as? String ?? ""
let defaultAccount = input["default_account"] as? String ?? ""

guard let (_, appElement) = remindersApp() else {
    stdoutJSON(["ok": false, "error": "Accessibility permission required or Reminders is not running"])
    exit(0)
}

if action == "catalog" {
    guard let outline = sidebarOutline(appElement) else {
        stdoutJSON(["ok": false, "error": "sidebar not found"])
        exit(0)
    }
    let includeGroups = input["include_groups"] as? Bool ?? false
    stdoutJSON(["ok": true, "lists": sidebarCatalog(outline, defaultAccount: defaultAccount, includeGroups: includeGroups)])
    exit(0)
}

if action == "create_group" {
    let groupName = input["group_name"] as? String ?? ""
    stdoutJSON(createGroup(appElement: appElement, defaultAccount: defaultAccount, groupName: groupName))
    exit(0)
}

if action == "create_list" {
    let parentPath = input["parent_path"] as? String ?? ""
    let listName = input["list_name"] as? String ?? ""
    stdoutJSON(createList(appElement: appElement, defaultAccount: defaultAccount, parentPath: parentPath, listName: listName))
    exit(0)
}

if action == "debug_row_menu" {
    let path = input["path"] as? String ?? ""
    stdoutJSON(["ok": true, "titles": rowMenuTitles(appElement: appElement, defaultAccount: defaultAccount, path: path)])
    exit(0)
}

if action == "create_section" {
    let listPath = input["list_path"] as? String ?? ""
    let sectionName = input["section_name"] as? String ?? ""
    stdoutJSON(createSection(appElement: appElement, listPath: listPath, defaultAccount: defaultAccount, sectionName: sectionName))
    exit(0)
}

let listPath = input["list_path"] as? String ?? ""
guard let selectedName = selectList(appElement, path: listPath, defaultAccount: defaultAccount) else {
    stdoutJSON(["ok": false, "error": "list not found"])
    exit(0)
}

if action == "list_reminders" {
    guard let outline = detailOutline(appElement, selectedName: selectedName) else {
        stdoutJSON(["ok": false, "error": "detail list not found"])
        exit(0)
    }
    let limit = max(1, input["limit"] as? Int ?? 50)
    let requestedSectionName = input["section_name"] as? String ?? ""
    let items = reminderRows(outline)
        .filter { requestedSectionName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || normalizedText($0.sectionName) == normalizedText(requestedSectionName) }
        .prefix(limit)
        .map { row in
        [
            "name": row.name,
            "body": row.body,
            "due_date": "",
            "completed": row.completed ? "true" : "false",
            "section_name": row.sectionName,
        ]
    }
    stdoutJSON(["ok": true, "reminders": Array(items)])
    exit(0)
}

if action == "list_sections" {
    guard let outline = detailOutline(appElement, selectedName: selectedName) else {
        stdoutJSON(["ok": false, "error": "detail list not found"])
        exit(0)
    }
    stdoutJSON(["ok": true, "sections": sectionNames(outline)])
    exit(0)
}

if action == "create_reminder" {
    let name = input["name"] as? String ?? ""
    let note = input["notes"] as? String ?? ""
    let sectionName = input["section_name"] as? String ?? ""
    let triggerStrategy = input["trigger_strategy"] as? String ?? ""
    stdoutJSON(createReminder(appElement: appElement, listPath: listPath, defaultAccount: defaultAccount, name: name, note: note, sectionName: sectionName, triggerStrategy: triggerStrategy))
    exit(0)
}

guard let outline = detailOutline(appElement, selectedName: selectedName) else {
    stdoutJSON(["ok": false, "error": "detail list not found"])
    exit(0)
}
guard let spec = input["spec"] as? JSONObject else {
    stdoutJSON(["ok": false, "error": "reminder selector missing"])
    exit(0)
}
guard let row = matchingRow(reminderRows(outline), spec: spec) else {
    stdoutJSON(["ok": false, "error": "reminder not found"])
    exit(0)
}

if action == "annotate_reminder" {
    let note = input["note"] as? String ?? ""
    stdoutJSON(["ok": setReminderBody(row, note: note)])
    exit(0)
}

if action == "complete_reminder" {
    let note = input["note"] as? String ?? ""
    if !note.isEmpty {
        _ = setReminderBody(row, note: note)
    }
    stdoutJSON(["ok": perform(row.checkbox, action: kAXPressAction as String)])
    exit(0)
}

if action == "move_to_section" {
    let targetSectionName = input["target_section_name"] as? String ?? ""
    stdoutJSON(["ok": moveReminderToSection(appElement: appElement, row: row.row, targetSectionName: targetSectionName)])
    exit(0)
}

stdoutJSON(["ok": false, "error": "unknown action"])
'''

_MODULE_CACHE_PATH = os.path.join(tempfile.gettempdir(), "apple-flow-swift-module-cache")
_HELPER_SCRIPT_PATH = os.path.join(tempfile.gettempdir(), "apple-flow-reminders-ax-helper.swift")
_HELPER_BINARY_PATH = os.path.join(tempfile.gettempdir(), "apple-flow-reminders-ax-helper")
existing_helper_source = ""
if os.path.exists(_HELPER_SCRIPT_PATH):
    with open(_HELPER_SCRIPT_PATH, "r", encoding="utf-8") as helper_file:
        existing_helper_source = helper_file.read()
if existing_helper_source != _SWIFT_HELPER:
    with open(_HELPER_SCRIPT_PATH, "w", encoding="utf-8") as helper_file:
        helper_file.write(_SWIFT_HELPER)
os.makedirs(_MODULE_CACHE_PATH, exist_ok=True)


def _ensure_helper_binary() -> str | None:
    try:
        script_mtime = os.path.getmtime(_HELPER_SCRIPT_PATH)
        binary_mtime = os.path.getmtime(_HELPER_BINARY_PATH) if os.path.exists(_HELPER_BINARY_PATH) else -1
        if binary_mtime >= script_mtime:
            return _HELPER_BINARY_PATH
        result = subprocess.run(
            [
                "swiftc",
                "-O",
                "-module-cache-path",
                _MODULE_CACHE_PATH,
                _HELPER_SCRIPT_PATH,
                "-o",
                _HELPER_BINARY_PATH,
            ],
            capture_output=True,
            text=True,
            timeout=120.0,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Compiling Reminders Accessibility helper timed out")
        return None
    except FileNotFoundError:
        logger.warning("swiftc not found — Reminders Accessibility fallback requires Xcode command line tools")
        return None
    except Exception as exc:
        logger.warning("Unexpected error compiling Reminders Accessibility helper: %s", exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "Compiling Reminders Accessibility helper failed (rc=%s): %s",
            result.returncode,
            (result.stderr or "").strip(),
        )
        return None
    return _HELPER_BINARY_PATH


def _run_helper(payload: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    helper_binary = _ensure_helper_binary()
    if helper_binary is None:
        return {"ok": False, "error": "helper unavailable"}
    try:
        result = subprocess.run(
            [helper_binary],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Reminders Accessibility helper timed out after %.1fs", timeout)
        return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        logger.warning("swift not found — Reminders Accessibility fallback requires Xcode command line tools")
        return {"ok": False, "error": "swift unavailable"}
    except Exception as exc:
        logger.warning("Unexpected error running Reminders Accessibility helper: %s", exc)
        return {"ok": False, "error": str(exc)}

    if result.returncode != 0:
        logger.warning(
            "Reminders Accessibility helper failed (rc=%s): %s",
            result.returncode,
            (result.stderr or "").strip(),
        )
        return {"ok": False, "error": (result.stderr or "").strip() or "swift helper failed"}

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        logger.warning("Reminders Accessibility helper returned invalid JSON: %r", result.stdout)
        return {"ok": False, "error": "invalid json"}

    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid response"}
    return payload


def _account_hint(default_account: str = "") -> str:
    return (default_account or "").strip()


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _encode_spec(spec: dict[str, Any]) -> str:
    raw = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{AX_REMINDER_ID_PREFIX}{token}"


def is_accessibility_id(reminder_id: str) -> bool:
    return (reminder_id or "").startswith(AX_REMINDER_ID_PREFIX)


def is_ax_reminder_id(reminder_id: str) -> bool:
    """Backward-compatible alias for callers using the shorter helper name."""
    return is_accessibility_id(reminder_id)


def _decode_spec(reminder_id: str) -> dict[str, Any] | None:
    if not is_accessibility_id(reminder_id):
        return None
    token = reminder_id[len(AX_REMINDER_ID_PREFIX):]
    padding = "=" * (-len(token) % 4)
    try:
        payload = base64.urlsafe_b64decode(token + padding)
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def list_catalog(default_account: str = "", include_groups: bool = False) -> list[dict[str, Any]]:
    result = _run_helper(
        {
            "action": "catalog",
            "default_account": _account_hint(default_account),
            "include_groups": bool(include_groups),
        },
        timeout=25.0,
    )
    if not result.get("ok"):
        return []
    data = result.get("lists")
    return data if isinstance(data, list) else []


def _run_system_events(script: str, timeout: float = 20.0) -> dict[str, Any]:
    result = run_osascript_with_recovery(
        script,
        app_name="Reminders",
        timeout=timeout,
        max_attempts=2,
    )
    return {"ok": result.ok, "error": result.detail if not result.ok else "", "stdout": result.stdout}


def _dismiss_reminders_sheet() -> None:
    script = (
        'tell application "System Events"\n'
        '  tell process "Reminders"\n'
        '    try\n'
        '      if exists sheet 1 of front window then\n'
        '        try\n'
        '          click button "Cancel" of group 1 of sheet 1 of front window\n'
        '        on error\n'
        '          key code 53\n'
        '        end try\n'
        '      end if\n'
        '    end try\n'
        '  end tell\n'
        'end tell'
    )
    _run_system_events(script, timeout=5.0)


def _detail_ui_get(spec: str) -> str:
    result = run_osascript_with_recovery(
        f'tell application "System Events" to tell process "Reminders" to get value of {spec}',
        app_name="Reminders",
        timeout=10.0,
        max_attempts=2,
    )
    return result.stdout.strip() if result.ok else ""


def _find_placeholder_row(section_name: str, max_rows: int = 80) -> int | None:
    target = (section_name or "").strip()
    if not target:
        return None
    expected = f"New reminder in {target}"
    for row_index in range(1, max_rows + 1):
        desc = _detail_ui_get(
            f'attribute "AXDescription" of button 1 of UI element 1 of row {row_index} of {_DETAIL_OUTLINE_SPEC}'
        )
        if desc == expected:
            return row_index
    return None


def _create_reminder_via_system_events(list_path: str, name: str, section_name: str = "") -> bool:
    if not focus_list(list_path):
        return False
    escaped_name = name.replace("\\", "\\\\").replace('"', '\\"')
    if section_name.strip():
        placeholder_row = _find_placeholder_row(section_name)
        if placeholder_row is None:
            return False
        script = (
            'tell application "System Events"\n'
            '  tell process "Reminders"\n'
            f'    click button 1 of UI element 1 of row {placeholder_row} of {_DETAIL_OUTLINE_SPEC}\n'
            f'    keystroke "{escaped_name}"\n'
            '    key code 36\n'
            '  end tell\n'
            'end tell'
        )
    else:
        script = (
            'tell application "System Events"\n'
            '  tell process "Reminders"\n'
            '    click menu bar item "File" of menu bar 1\n'
            '    click menu item "New Reminder" of menu 1 of menu bar item "File" of menu bar 1\n'
            f'    keystroke "{escaped_name}"\n'
            '    key code 36\n'
            '  end tell\n'
            'end tell'
        )
    result = _run_system_events(script, timeout=20.0)
    if not result.get("ok"):
        return False
    return _wait_for(
        lambda: any(
            _normalize_name(str(item.get("name", ""))) == _normalize_name(name)
            and (
                not section_name.strip()
                or _normalize_name(str(item.get("section_name", ""))) == _normalize_name(section_name)
            )
            for item in list_reminders(
                list_path,
                filter_completed="all",
                limit=200,
                section_name=section_name,
            )
        ),
        timeout_seconds=12.0,
    )


def _sidebar_row_label(row_index: int) -> str:
    specs = (
        f'text field 1 of UI element 1 of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}',
        f'static text 1 of UI element 1 of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}',
    )
    for spec in specs:
        result = run_osascript_with_recovery(
            f'tell application "System Events" to tell process "Reminders" to get value of {spec}',
            app_name="Reminders",
            timeout=5.0,
            max_attempts=1,
        )
        value = result.stdout.strip() if result.ok else ""
        if value:
            return value
    return ""


def _find_sidebar_row(label: str, limit: int = 80) -> int | None:
    target = (label or "").strip()
    if not target:
        return None
    for row_index in range(1, limit + 1):
        if _sidebar_row_label(row_index) == target:
            return row_index
    return None


def _selected_sidebar_row(limit: int = 80) -> int | None:
    for row_index in range(1, limit + 1):
        result = run_osascript_with_recovery(
            (
                'tell application "System Events" to tell process "Reminders" '
                f'to value of attribute "AXSelected" of row {row_index} of {_SIDEBAR_OUTLINE_SPEC} as text'
            ),
            app_name="Reminders",
            timeout=5.0,
            max_attempts=1,
        )
        if result.ok and result.stdout.strip() == "true":
            return row_index
    return None


def _sidebar_row_description(row_index: int) -> str:
    result = run_osascript_with_recovery(
        (
            'tell application "System Events" to tell process "Reminders" '
            f'to get description of UI element 1 of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}'
        ),
        app_name="Reminders",
        timeout=5.0,
        max_attempts=1,
    )
    return result.stdout.strip() if result.ok else ""


def _sidebar_row_rect(row_index: int) -> tuple[float, float, float, float] | None:
    pos = run_osascript_with_recovery(
        (
            'tell application "System Events" to tell process "Reminders" '
            f'to get value of attribute "AXPosition" of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}'
        ),
        app_name="Reminders",
        timeout=5.0,
        max_attempts=1,
    )
    size = run_osascript_with_recovery(
        (
            'tell application "System Events" to tell process "Reminders" '
            f'to get value of attribute "AXSize" of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}'
        ),
        app_name="Reminders",
        timeout=5.0,
        max_attempts=1,
    )
    if not pos.ok or not size.ok:
        return None
    try:
        x_text, y_text = [part.strip() for part in pos.stdout.split(",", 1)]
        w_text, h_text = [part.strip() for part in size.stdout.split(",", 1)]
        return (float(x_text), float(y_text), float(w_text), float(h_text))
    except (ValueError, IndexError):
        return None


def _sidebar_row_name_parts(row_index: int) -> tuple[str, str]:
    label = _sidebar_row_label(row_index).strip()
    description = _sidebar_row_description(row_index).strip()
    source = label or description
    name = source.split(",", 1)[0].strip() if source else ""
    parent_group = ""
    marker = " in group "
    if marker in description:
        parent_group = description.rsplit(marker, 1)[-1].strip()
    return name, parent_group


def _sidebar_rows(limit: int = 80, *, include_rects: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index in range(1, limit + 1):
        label = _sidebar_row_label(row_index).strip()
        description = _sidebar_row_description(row_index).strip()
        if not label and not description:
            continue
        name, parent_group = _sidebar_row_name_parts(row_index)
        rows.append(
            {
                "row": row_index,
                "label": label,
                "description": description,
                "name": name,
                "parent_group": parent_group,
                "is_group": bool(label) and description == "cell",
                "rect": _sidebar_row_rect(row_index) if include_rects else None,
            }
        )
    return rows


def _find_group_row(name: str, limit: int = 80) -> dict[str, Any] | None:
    target = (name or "").strip()
    if not target:
        return None
    for row in _sidebar_rows(limit=limit):
        if row["is_group"] and row["label"] == target:
            return row
    return None


def _find_top_level_list_row(name: str, limit: int = 80) -> dict[str, Any] | None:
    target = (name or "").strip()
    if not target:
        return None
    for row in _sidebar_rows(limit=limit):
        if row["is_group"]:
            continue
        if row["name"] == target and not row["parent_group"]:
            return row
    return None


def _find_nested_list_row(name: str, parent_group: str, limit: int = 80) -> dict[str, Any] | None:
    target = (name or "").strip()
    target_parent = (parent_group or "").strip()
    if not target or not target_parent:
        return None
    for row in _sidebar_rows(limit=limit):
        if row["is_group"]:
            continue
        if row["name"] == target and row["parent_group"] == target_parent:
            return row
    return None


def _find_sidebar_row_for_path(list_path: str, limit: int = 80) -> dict[str, Any] | None:
    parts = [part.strip() for part in (list_path or "").split("/") if part.strip()]
    if len(parts) >= 3:
        return _find_nested_list_row(parts[-1], parts[-2], limit=limit)
    if len(parts) == 2:
        return _find_group_row(parts[-1], limit=limit) or _find_top_level_list_row(parts[-1], limit=limit)
    return None


def _select_sidebar_row(row_index: int) -> bool:
    result = _run_system_events(
        (
            'tell application "System Events"\n'
            '  tell process "Reminders"\n'
            f'    click UI element 1 of row {row_index} of {_SIDEBAR_OUTLINE_SPEC}\n'
            '  end tell\n'
            'end tell'
        ),
        timeout=10.0,
    )
    return bool(result.get("ok"))


def focus_list(list_path: str) -> bool:
    row = _find_sidebar_row_for_path(list_path)
    if row is None:
        return False
    return _select_sidebar_row(int(row["row"]))


def _delete_top_level_list_by_name(name: str) -> bool:
    escaped_name = name.replace("\\", "\\\\").replace('"', '\\"')
    result = run_osascript_with_recovery(
        (
            'tell application "Reminders"\n'
            f'  delete (first list whose name is "{escaped_name}")\n'
            'end tell'
        ),
        app_name="Reminders",
        timeout=20.0,
        max_attempts=2,
    )
    return result.ok


def _helper_list_path_exists(path: str, default_account: str = "") -> bool:
    target = (path or "").strip()
    if not target:
        return False
    for entry in list_catalog(default_account=default_account):
        if str(entry.get("path", "")).strip() == target:
            return True
    return False


def _wait_for(predicate, timeout_seconds: float = 8.0, interval_seconds: float = 0.25) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval_seconds)
    return bool(predicate())


def create_group(group_name: str, default_account: str = "") -> dict[str, Any]:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.create_group"):
        group_path = "/".join(part for part in (_account_hint(default_account), group_name) if part)
        helper_result = _run_helper(
            {
                "action": "create_group",
                "default_account": _account_hint(default_account),
                "group_name": group_name,
            },
            timeout=25.0,
        )
        if helper_result.get("ok"):
            return {
                "ok": True,
                "status": str(helper_result.get("status", "created")),
                "path": str(helper_result.get("path") or group_path),
            }
        helper_error = str(helper_result.get("error") or "")
        if helper_error and helper_error != "helper unavailable":
            return {"ok": False, "error": helper_error}

        existing_group = _find_group_row(group_name)
        if existing_group is not None:
            return {"ok": True, "status": "exists", "path": group_path}

        flat_conflict = _find_top_level_list_row(group_name)
        if flat_conflict is not None:
            if not _delete_top_level_list_by_name(group_name):
                return {"ok": False, "error": "unable to remove conflicting top-level list"}
            if not _wait_for(lambda: _find_top_level_list_row(group_name) is None, timeout_seconds=8.0):
                return {"ok": False, "error": "conflicting top-level list did not disappear"}

        escaped_name = group_name.replace("\\", "\\\\").replace('"', '\\"')
        fallback = _run_system_events(
            (
                'tell application "System Events"\n'
                '  tell process "Reminders"\n'
                '    click menu bar item "File" of menu bar 1\n'
                '    click menu item "New Group" of menu 1 of menu bar item "File" of menu bar 1\n'
                '  end tell\n'
                'end tell'
            ),
            timeout=20.0,
        )
        if not fallback.get("ok"):
            return {"ok": False, "error": fallback.get("error") or "unable to create group"}
        row_index = _selected_sidebar_row()
        if row_index is None:
            return {"ok": False, "error": "new group row not selected"}
        rename = _run_system_events(
            (
                'tell application "System Events"\n'
                '  tell process "Reminders"\n'
                f'    set value of text field 1 of UI element 1 of row {row_index} of {_SIDEBAR_OUTLINE_SPEC} to "{escaped_name}"\n'
                '    key code 36\n'
                '  end tell\n'
                'end tell'
            ),
            timeout=20.0,
        )
        if not rename.get("ok"):
            return {"ok": False, "error": rename.get("error") or "unable to name group"}
        if _wait_for(lambda: _find_group_row(group_name) is not None, timeout_seconds=8.0):
            return {"ok": True, "status": "created", "path": group_path}
        return {"ok": False, "error": "group did not appear"}


def create_list(parent_path: str, list_name: str) -> dict[str, Any]:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.create_list"):
        list_path = "/".join(part for part in (parent_path, list_name) if part)
        account_name = parent_path.split("/", 1)[0] if "/" in parent_path else ""

        if _helper_list_path_exists(list_path, default_account=account_name):
            return {"ok": True, "status": "exists", "path": list_path}

        helper_result = _run_helper(
            {
                "action": "create_list",
                "default_account": account_name,
                "parent_path": parent_path,
                "list_name": list_name,
            },
            timeout=30.0,
        )
        if helper_result.get("ok"):
            return {
                "ok": True,
                "status": str(helper_result.get("status", "created")),
                "path": str(helper_result.get("path") or list_path),
            }
        helper_error = str(helper_result.get("error") or "unable to create nested list")
        _dismiss_reminders_sheet()
        top_level_target_path = "/".join(part for part in (account_name, list_name) if part)
        if (
            top_level_target_path
            and _helper_list_path_exists(top_level_target_path, default_account=account_name)
            and not _helper_list_path_exists(list_path, default_account=account_name)
        ):
            _delete_top_level_list_by_name(list_name)

        if _helper_list_path_exists(list_path, default_account=account_name):
            return {"ok": True, "status": "exists", "path": list_path}
        if helper_error == "helper unavailable":
            parent_name = parent_path.rsplit("/", 1)[-1].strip()
            existing_nested = _find_nested_list_row(list_name, parent_name)
            if existing_nested is not None:
                return {"ok": True, "status": "exists", "path": list_path}
            return {"ok": False, "error": "helper unavailable"}
        return {"ok": False, "error": helper_error}


def _synthesize_reminder_id(
    list_path: str,
    name: str,
    body: str,
    ordinal: int,
    section_name: str = "",
) -> str:
    return _encode_spec(
        {
            "list_path": list_path,
            "name": name,
            "body_prefix": (body or "")[:120],
            "ordinal": ordinal,
            "section_name": section_name,
        }
    )


def list_reminders(
    list_path: str,
    filter_completed: str = "incomplete",
    limit: int = 50,
    section_name: str = "",
) -> list[dict[str, Any]]:
    del filter_completed  # Accessibility currently exposes visible rows only.
    result = _run_helper(
        {
            "action": "list_reminders",
            "list_path": list_path,
            "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
            "limit": int(limit),
            "section_name": section_name,
        },
        timeout=25.0,
    )
    if not result.get("ok"):
        return []

    reminders = result.get("reminders")
    if not isinstance(reminders, list):
        return []

    counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    output: list[dict[str, Any]] = []
    for item in reminders:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        body = str(item.get("body", ""))
        due_date = str(item.get("due_date", ""))
        item_section_name = str(item.get("section_name", ""))
        key = (_normalize_name(name), due_date, _normalize_name(item_section_name))
        counts[key] += 1
        ordinal = counts[key]
        output.append(
            {
                "id": _synthesize_reminder_id(list_path, name, body, ordinal, section_name=item_section_name),
                "name": name,
                "body": body,
                "due_date": due_date,
                "completed": str(item.get("completed", "false")),
                "list": list_path.rsplit("/", 1)[-1],
                "list_id": "",
                "list_path": list_path,
                "section_name": item_section_name,
                "source": "accessibility",
            }
        )
    return output


def list_sections(list_path: str) -> list[str]:
    result = _run_helper(
        {
            "action": "list_sections",
            "list_path": list_path,
            "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
        },
        timeout=25.0,
    )
    if not result.get("ok"):
        return []
    sections = result.get("sections")
    if not isinstance(sections, list):
        return []
    return [str(section) for section in sections if str(section).strip()]


def _create_section_via_system_events(list_path: str, section_name: str) -> dict[str, Any]:
    if not focus_list(list_path):
        return {"ok": False, "error": "list not found"}
    escaped_name = section_name.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "System Events"\n'
        '  tell process "Reminders"\n'
        '    click menu bar item "File" of menu bar 1\n'
        '    click menu item "New Section" of menu 1 of menu bar item "File" of menu bar 1\n'
        f'    keystroke "{escaped_name}"\n'
        '    key code 36\n'
        '  end tell\n'
        'end tell'
    )
    result = _run_system_events(script, timeout=20.0)
    if not result.get("ok"):
        return {"ok": False, "error": str(result.get("error") or "unable to trigger new section")}
    if _wait_for(
        lambda: any(
            _normalize_name(existing) == _normalize_name(section_name)
            for existing in list_sections(list_path)
        ),
        timeout_seconds=10.0,
    ):
        return {"ok": True, "status": "created", "section_name": section_name}
    return {"ok": False, "error": "section did not appear"}


def create_section(list_path: str, section_name: str) -> dict[str, Any]:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.create_section"):
        clean_section_name = (section_name or "").strip()
        if not clean_section_name:
            return {"ok": False, "error": "section name is required"}
        if any(_normalize_name(existing) == _normalize_name(clean_section_name) for existing in list_sections(list_path)):
            return {"ok": True, "status": "exists", "section_name": clean_section_name}
        result = _run_helper(
            {
                "action": "create_section",
                "list_path": list_path,
                "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
                "section_name": clean_section_name,
            },
            timeout=25.0,
        )
        if not result.get("ok"):
            helper_error = str(result.get("error") or "unable to create section")
            if helper_error in {
                "section title field not focused",
                "unable to set section name",
                "section did not appear",
                "unable to trigger new section",
            }:
                fallback = _create_section_via_system_events(list_path, clean_section_name)
                if fallback.get("ok"):
                    return fallback
            return {"ok": False, "error": helper_error}
        return {
            "ok": True,
            "status": str(result.get("status", "created")),
            "section_name": str(result.get("section_name") or clean_section_name),
        }


def create_reminder(
    list_path: str,
    name: str,
    notes: str = "",
    due_date: str = "",
    section_name: str = "",
) -> str | None:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.create_reminder"):
        if due_date:
            logger.warning(
                "Accessibility fallback does not yet support due_date for reminder creation in %r",
                list_path,
            )
        payload = {
            "action": "create_reminder",
            "list_path": list_path,
            "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
            "name": name,
            "notes": notes,
            "section_name": section_name,
        }
        result = _run_helper(payload, timeout=25.0)
        if not result.get("ok") and result.get("error") == "unable to trigger new reminder":
            result = _run_helper({**payload, "trigger_strategy": "menu"}, timeout=25.0)
        if not result.get("ok"):
            if _create_reminder_via_system_events(list_path, name, section_name=section_name):
                if notes:
                    logger.warning(
                        "System Events fallback created reminder without inline notes support in %r",
                        list_path,
                    )
                return _synthesize_reminder_id(list_path, name, notes, 1, section_name=section_name)
            return None
        return _synthesize_reminder_id(list_path, name, notes, 1, section_name=section_name)


def complete_reminder(
    list_path: str,
    reminder_id: str,
    note: str = "",
    section_name: str = "",
) -> bool:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.complete_reminder"):
        spec = _decode_spec(reminder_id)
        if spec is None:
            return False
        if section_name:
            spec["section_name"] = section_name
        result = _run_helper(
            {
                "action": "complete_reminder",
                "list_path": list_path,
                "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
                "spec": spec,
                "note": note,
            },
            timeout=25.0,
        )
        return bool(result.get("ok"))


def annotate_reminder(
    list_path: str,
    reminder_id: str,
    note: str,
    section_name: str = "",
) -> bool:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.annotate_reminder"):
        spec = _decode_spec(reminder_id)
        if spec is None:
            return False
        if section_name:
            spec["section_name"] = section_name
        result = _run_helper(
            {
                "action": "annotate_reminder",
                "list_path": list_path,
                "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
                "spec": spec,
                "note": note,
            },
            timeout=25.0,
        )
        return bool(result.get("ok"))


def move_to_archive(reminder_id: str, source_list_path: str, archive_list_path: str, result_text: str) -> bool:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.move_to_archive"):
        spec = _decode_spec(reminder_id)
        if spec is None:
            return False
        source_items = list_reminders(
            source_list_path,
            limit=200,
            section_name=str(spec.get("section_name", "") or ""),
        )
        matched = next((item for item in source_items if item.get("id") == reminder_id), None)
        title = str((matched or {}).get("name") or spec.get("name") or "")
        if not title:
            return False
        if create_reminder(archive_list_path, title, notes=result_text) is None:
            return False
        return complete_reminder(
            source_list_path,
            reminder_id,
            note=result_text,
            section_name=str(spec.get("section_name", "") or ""),
        )


def move_to_section(list_path: str, reminder_id: str, target_section_name: str) -> bool:
    with reminders_runtime_gate.reminders_live_gate(reason="reminders_accessibility.move_to_section"):
        spec = _decode_spec(reminder_id)
        if spec is None:
            return False
        result = _run_helper(
            {
                "action": "move_to_section",
                "list_path": list_path,
                "default_account": list_path.split("/", 1)[0] if "/" in list_path else "",
                "spec": spec,
                "target_section_name": target_section_name,
            },
            timeout=25.0,
        )
        return bool(result.get("ok"))
