#Requires AutoHotkey v2.0
#SingleInstance Force
#UseHook true
Persistent

; === Globals ===
global Locked := false
global LockedHwnd := 0
global HoldStart := 0
global F1Holding := false           ; Guard gegen Key-Repeat
global UnlockThreshold := 3000
global LockGui := 0
global ProgressGui := 0
global ProgressBar := 0
global JustUnlocked := false

; === Watchdog: Fenster noch da? ===
SetTimer(WatchLockedWindow, 500)

WatchLockedWindow() {
    global Locked, LockedHwnd
    if Locked && LockedHwnd && !WinExist("ahk_id " LockedHwnd)
        ForceUnlock()
}

; =================================================================
; F1 DOWN
; =================================================================
F1:: {
    global Locked, LockedHwnd, HoldStart, JustUnlocked, F1Holding

    ; *** KEY-REPEAT GUARD ***
    ; Wenn F1 schon gehalten wird → ignorieren, HoldStart nicht resetten
    if F1Holding
        return
    F1Holding := true

    JustUnlocked := false
    HoldStart := A_TickCount

    if Locked && LockedHwnd && WinExist("ahk_id " LockedHwnd) {
        ShowProgressOverlay(LockedHwnd)
        SetTimer(UpdateProgress, 50)
    }
}

; =================================================================
; F1 UP
; =================================================================
F1 Up:: {
    global Locked, LockedHwnd, JustUnlocked, F1Holding

    F1Holding := false              ; Guard zurücksetzen
    SetTimer(UpdateProgress, 0)
    HideProgressOverlay()

    if JustUnlocked {
        JustUnlocked := false
        return
    }

    if !Locked {
        try {
            hwnd := WinGetID("A")
            if hwnd {
                LockedHwnd := hwnd
                LockCursor(hwnd)
                ShowLockedOverlay(hwnd)
				HideTaskbar()
                Locked := true
            }
        }
    }
}

; =================================================================
; Progress-Timer
; =================================================================
UpdateProgress() {
    global HoldStart, UnlockThreshold, Locked, LockedHwnd, ProgressBar, JustUnlocked

    if !Locked || !LockedHwnd || !WinExist("ahk_id " LockedHwnd) {
        ForceUnlock()
        return
    }

    elapsed := A_TickCount - HoldStart
    pct := Min(100, Floor((elapsed / UnlockThreshold) * 100))

    try {
        if ProgressBar
            ProgressBar.Value := pct
    }

    if elapsed >= UnlockThreshold {
        JustUnlocked := true
        ForceUnlock()
    }
}

; =================================================================
; Unlock
; =================================================================
ForceUnlock() {
    global Locked, LockedHwnd
    SetTimer(UpdateProgress, 0)
    UnlockCursor()
	ShowTaskbar()
    HideProgressOverlay()
    HideLockedOverlay()
    Locked := false
    LockedHwnd := 0
}

; =================================================================
; Taskbar verstecken / sichtbar machen
; =================================================================
; Hide the taskbar
HideTaskbar() {
    WinHide "ahk_class Shell_TrayWnd"
    WinHide "ahk_class Shell_SecondaryTrayWnd"  ; For multi-monitor setups
}

; Show the taskbar
ShowTaskbar() {
    WinShow "ahk_class Shell_TrayWnd"
    WinShow "ahk_class Shell_SecondaryTrayWnd"  ; For multi-monitor setups
}

; =================================================================
; Alt+Tab blockieren (nur wenn gelockt)
; =================================================================
#HotIf Locked
!Tab::return
!+Tab::return
LWin::return
RWin::return
LWin Up::return
RWin Up::return
#HotIf

; =================================================================
; Cursor-Clipping
; =================================================================
LockCursor(hwnd) {
    WinGetPos(&X, &Y, &W, &H, "ahk_id " hwnd)
    pad := 12  ; Pixel nach innen – verhindert Resize-Griffe & Taskleisten-Kontakt
    R := Buffer(16, 0)
    NumPut("Int", X + pad,     R, 0)
    NumPut("Int", Y + pad,     R, 4)
    NumPut("Int", X + W - pad, R, 8)
    NumPut("Int", Y + H - pad, R, 12)
    DllCall("ClipCursor", "Ptr", R)
}

UnlockCursor() {
    DllCall("ClipCursor", "Ptr", 0)
}

; =================================================================
; FOCUS-Badge + Unlock-Hinweis (dauerhaft sichtbar)
; =================================================================
ShowLockedOverlay(hwnd) {
    global LockGui
    HideLockedOverlay()

    WinGetPos(&X, &Y, &W,, "ahk_id " hwnd)

    LockGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20")
    LockGui.BackColor := "1a1a2e"
    LockGui.MarginX := 10
    LockGui.MarginY := 6
    LockGui.SetFont("s9 Bold", "Segoe UI")
    LockGui.AddText("c44cc88 Center w140", "🔒 FOCUS")
    LockGui.SetFont("s7 Norm", "Segoe UI")
    LockGui.AddText("c888888 Center w140", "Hold F1 (3s) to unlock")
    LockGui.Show("x" (X + W - 185) " y" (Y + 12) " NoActivate")
    WinSetTransparent(210, LockGui)
}

HideLockedOverlay() {
    global LockGui
    if LockGui {
        try LockGui.Destroy()
        LockGui := 0
    }
}

; =================================================================
; Progress-Bar (nur während F1 gehalten, unten mittig)
; =================================================================
ShowProgressOverlay(hwnd) {
    global ProgressGui, ProgressBar
    HideProgressOverlay()

    WinGetPos(&X, &Y, &W, &H, "ahk_id " hwnd)

    ProgressGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20")
    ProgressGui.BackColor := "1a1a2e"
    ProgressGui.MarginX := 12
    ProgressGui.MarginY := 8
    ProgressGui.SetFont("s8", "Segoe UI")
    ProgressGui.AddText("cCCCCCC Center w180", "Unlocking...")
    ProgressBar := ProgressGui.AddProgress("w180 h5 c44cc88 Background333333", 0)
    ProgressGui.Show("x" (X + (W // 2) - 102) " y" (Y + H - 65) " NoActivate")
    WinSetTransparent(230, ProgressGui)
}

HideProgressOverlay() {
    global ProgressGui, ProgressBar
    if ProgressGui {
        try ProgressGui.Destroy()
        ProgressGui := 0
        ProgressBar := 0
    }
}
