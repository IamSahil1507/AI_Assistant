Attribute VB_Name = "OpenClawAddin"
Option Explicit

Private Function JsonEscape(ByVal s As String) As String
    s = Replace(s, "\\", "\\\\")
    s = Replace(s, "\"", "\\\"")
    s = Replace(s, vbCrLf, "\\n")
    s = Replace(s, vbCr, "\\n")
    s = Replace(s, vbLf, "\\n")
    JsonEscape = s
End Function

Private Function HttpPostJson(ByVal url As String, ByVal body As String) As String
    Dim http As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.Open "POST", url, False
    http.SetRequestHeader "Content-Type", "application/json"
    http.Send body
    HttpPostJson = http.ResponseText
End Function

Private Function ExtractMessage(ByVal json As String) As String
    Dim startPos As Long, endPos As Long
    startPos = InStr(1, json, "\"content\"")
    If startPos = 0 Then
        ExtractMessage = json
        Exit Function
    End If
    startPos = InStr(startPos, json, "\"") + 1
    startPos = InStr(startPos, json, "\"") + 1
    startPos = InStr(startPos, json, "\"") + 1
    endPos = InStr(startPos, json, "\"")
    If endPos <= startPos Then
        ExtractMessage = json
    Else
        ExtractMessage = Mid$(json, startPos, endPos - startPos)
        ExtractMessage = Replace(ExtractMessage, "\\n", vbCrLf)
        ExtractMessage = Replace(ExtractMessage, "\\\"", "\"")
    End If
End Function
Public Function OPENCLAW(prompt As String, Optional inputRange As Variant) As String
    On Error GoTo ErrHandler
    Dim endpoint As String
    endpoint = "http://127.0.0.1:11435/v1/chat/completions"
    Dim inputText As String
    If IsMissing(inputRange) Then
        inputText = ""
    Else
        inputText = CStr(inputRange)
    End If
    Dim payload As String
    Dim fullPrompt As String
    If Len(inputText) > 0 Then
        fullPrompt = prompt & "\n\nInput: " & inputText
    Else
        fullPrompt = prompt
    End If
    payload = "{\"model\":\"awarenet:v1\",\"messages\":[{\"role\":\"user\",\"content\":\"" & JsonEscape(fullPrompt) & "\"}]}"
    Dim resp As String
    resp = HttpPostJson(endpoint, payload)
    OPENCLAW = ExtractMessage(resp)
    Exit Function
ErrHandler:
    OPENCLAW = "Error: " & Err.Description
End Function

Public Sub OpenClawChat()
    On Error Resume Next
    Dim prompt As String
    prompt = InputBox("Ask OpenClaw:", "OpenClaw")
    If Len(prompt) = 0 Then Exit Sub
    Dim result As String
    result = OPENCLAW(prompt)
    MsgBox result, vbInformation, "OpenClaw"
End Sub
