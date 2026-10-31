on open location theURL
	do shell script (quoted form of "@@VIBE@@") & " link-open " & (quoted form of theURL) & " </dev/null >/dev/null 2>&1 &"
end open location

on run
	display dialog "Vibe Link opens vibe:// links from Task&I. Run 'vibe link --status' in a terminal for details." buttons {"OK"} default button "OK" giving up after 30
end run
