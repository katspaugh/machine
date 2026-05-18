# VHS script (charmbracelet/vhs) that records the README demo gif.
# Render with: cd assets/demo && vhs machine.tape  (writes assets/machine.gif).
Output ../machine.gif

Set Shell "bash"
Set FontSize 16
Set Width 1100
Set Height 720
Set Theme "Dracula"
Set TypingSpeed 35ms
Set PlaybackSpeed 1.0
Set Padding 20

Hide
Type "alias machine='bash /Users/ivan/Sites/machine/assets/demo/machine-demo.sh'" Enter
Type "PS1=$'\\e[35m➜\\e[0m \\e[36mmachine\\e[0m $ '" Enter
Type "clear" Enter
Show

Type "# machine — one isolated Lima VM per project" Sleep 600ms Enter
Type "machine list" Sleep 300ms Enter
Sleep 2000ms

Type "machine up wallet" Sleep 300ms Enter
Sleep 7000ms

Type "machine status wallet" Sleep 300ms Enter
Sleep 1500ms

Type "machine secrets wallet" Sleep 300ms Enter
Sleep 2500ms

Type "machine ssh wallet" Sleep 300ms Enter
Sleep 6500ms

Type "machine down wallet" Sleep 300ms Enter
Sleep 1500ms
