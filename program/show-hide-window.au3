#include <AutoItConstants.au3>

AutoItSetOption("WinTitleMatchMode", 2)

Local $aList = WinList($CmdLine[1] & ".bat")

For $i = 1 To $aList[0][0]
    Local $iState = WinGetState($aList[$i][1])

    If BitAND($iState, $WIN_STATE_VISIBLE) Then
        WinSetState($aList[$i][1], "", @SW_HIDE)
    Else
        WinSetState($aList[$i][1], "", @SW_SHOW)
        WinActivate($aList[$i][1])
    EndIf    
Next

Local $aList = WinList("cmd.exe")

For $i = 1 To $aList[0][0]
    Local $iState = WinGetState($aList[$i][1])

    If BitAND($iState, $WIN_STATE_VISIBLE) Then
        WinSetState($aList[$i][1], "", @SW_HIDE)
    Else
        WinSetState($aList[$i][1], "", @SW_SHOW)
        WinActivate($aList[$i][1])
    EndIf    
Next