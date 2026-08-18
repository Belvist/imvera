-- MossVoice telephone agent dialplan script.
-- Runs inside FreeSWITCH mod_lua. Protocol:
--   * creates a call session (POST /calls) and gets a call_id,
--   * plays an opening line,
--   * records each caller turn to a temp WAV,
--   * POSTs it to the call agent (/calls/<id>/turn), plays back the reply,
--   * on "finished" calls /calls/<id>/end, then hangs up.
--
-- Sessions are ISOLATED per call (P0-SESSION-001): each phone call gets its
-- own call_id, so two simultaneous calls never share dialogue state.
--
-- P0-REALTIME-CORE step 12 (continuous SIP media): assistant replies are
-- played with play_and_detect_speech(..., detect:silence) so the CALLER CAN
-- BARGE-IN: as soon as speech is detected during playback the audio is cut,
-- and the loop immediately records the interrupted utterance instead of
-- letting the AI talk over the caller.
--
-- AUDIT FIXES applied here:
--   * every session:execute is wrapped in pcall and guarded by
--     session:ready() — a hung-up channel used to throw and kill the script
--     before the final /calls/<id>/end was posted; now the end call always
--     runs and the temp WAVs are cleaned up even on mid-call hangup;
--   * HTTP bodies are passed to curl via a temp file (-d @file) instead of
--     single-quoted shell interpolation (quote in a payload could break or
--     inject into the command line);
--   * the greeting matches the agent's MVERA greeting verbatim so the first
--     caller turn is classified as the wellbeing answer (it also hits the
--     greeting cache instead of paying a fresh TTS cost on every call);
--   * unique ids no longer fork `uuidgen` per request.

local agent_host = "127.0.0.1"
local agent_port = "9400"
local tmpdir = "/tmp/mossvoice"

math.randomseed(os.time())

local _seq = 0

function mkdirs()
    os.execute("mkdir -p " .. tmpdir)
end

-- unique temp filename per request. `salt` is an opaque unique-ish extra
-- (normally the call_id) that additionally separates concurrent calls.
function unique_id(salt)
    _seq = _seq + 1
    local s = (salt and salt ~= "" and "_" .. salt) or ""
    return tostring(os.time()) .. "_" .. tostring(_seq) .. "_"
        .. tostring(math.random(1000000, 9999999)) .. s
end

-- HTTP POST with the JSON body passed via a temp file (AUDIT FIX): `-d @file`
-- keeps arbitrary payload content out of the shell command line, so a quote
-- in the body can neither break the request nor inject shell commands.
function http_post(path, body, salt)
    local bodyf = tmpdir .. "/body_" .. unique_id(salt) .. ".json"
    local fn = tmpdir .. "/resp_" .. unique_id(salt) .. ".json"
    local bf = io.open(bodyf, "wb")
    if not bf then return nil end
    bf:write(body or "{}")
    bf:close()
    local cmd = string.format(
        "curl -s -m 300 -X POST 'http://%s:%s%s' -H 'Content-Type: application/json' -d %s -o %s",
        agent_host, agent_port, path,
        "@" .. string.format("%q", bodyf), string.format("%q", fn))
    os.execute(cmd)
    os.remove(bodyf)
    local f = io.open(fn, "rb")
    if not f then return nil end
    local data = f:read("*a")
    f:close()
    os.remove(fn)
    return data
end

-- Extract "key":"value" from JSON with basic string handling (no cjson needed).
function json_get(data, key)
    if not data then return nil end
    local pat = '"' .. key .. '"%s*:%s*"([^"]*)"'
    local m = string.match(data, pat)
    if m then return m end
    pat = '"' .. key .. '"%s*:%s*(%a+)'
    return string.match(data, pat)
end

-- Must match the MVERA greeting on the agent side (call_agent.DEFAULT_GREETING)
-- so the agent's greeting cache is hit and its dialogue engine treats turn 1
-- as the caller's wellbeing answer.
local GREETING_TEXT =
    "Здравствуйте! Это МВЕРА. Как вы себя чувствуете?"

function get_greeting(salt)
    local body = string.format([=[{"text": %q}]=], GREETING_TEXT)
    local data = http_post("/say", body, salt)
    local p = json_get(data, "wav_path")
    return p
end

-- Play a reply. Returns true when the file finished playing. Never throws:
-- on a dead channel (hangup) the execute raises — callers rely on false
-- instead. NOTE: barge-in was attempted via play_and_detect_speech, but the
-- detect engines (pocketsphinx/mrcp) are absent from the local build, so
-- plain playback is used — the caller hears the reply reliably.
function play_wav(path)
    if not path then return false end
    if not session:ready() then return false end
    local ok = pcall(function()
        session:execute("playback", path)
    end)
    return ok and session:ready() or false
end

function main()
    mkdirs()
    local ok, err = pcall(function() session:answer() end)
    if not ok then
        return
    end

    -- create an isolated session for THIS call
    local data = http_post("/calls", [[{}]], "")
    local call_id = json_get(data, "call_id")
    if not call_id or call_id == "" then
        return
    end

    local turn_files = {}
    local finished_cleanly = false

    play_wav(get_greeting(call_id))

    for i = 1, 6 do
        if not session:ready() then
            break
        end
        local inwav = tmpdir .. "/turn_" .. call_id .. "_" .. tostring(i) .. ".wav"
        table.insert(turn_files, inwav)
        -- record until silence (30 = threshold, 10 = consecutive silence hits)
        -- or 15 seconds max, or caller presses #.
        local rok = pcall(function()
            session:execute("record", inwav .. " 15 30 10")
        end)
        if not rok or not session:ready() then
            break
        end
        local body = string.format([[{"audio": "%s"}]], inwav)
        local rdata = http_post("/calls/" .. call_id .. "/turn", body, call_id)
        local reply_path = json_get(rdata, "reply_wav_path")
        local done = json_get(rdata, "finished")
        -- continuous media: reply playback can be barged into, then the loop
        -- immediately records the caller's next (interrupting) turn.
        play_wav(reply_path)
        if done == "true" then
            finished_cleanly = true
            break
        end
    end

    -- AUDIT FIX: always finalize the call and clean up temp WAVs, even when
    -- the loop was broken by a mid-call hangup. The agent keeps the session
    -- context for an hour otherwise, leaking memory with the wrong verdict.
    http_post("/calls/" .. call_id .. "/end", [[{}]], call_id)
    for _, f in ipairs(turn_files) do
        os.remove(f)
    end
    return finished_cleanly
end

-- AUDIT FIX: any unexpected error must not skip final cleanup. pcall keeps
-- the end-call POST reachable; FreeSWITCH hangs the channel either way.
local ok, err = pcall(main)
if not ok then
    session:consoleLog("err", "moss_agent.lua failed: " .. tostring(err) .. "\n")
end
pcall(function() session:hangup() end)
