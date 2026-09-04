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
local api_token = os.getenv("MOSS_INTERNAL_API_TOKEN") or ""
if api_token ~= "" and not string.match(api_token, "^[%w_%-]+$") then
    session:consoleLog("err", "MOSS_INTERNAL_API_TOKEN has invalid characters\n")
    api_token = ""
end

math.randomseed(os.time())

local _seq = 0

function mkdirs()
    os.execute("install -d -m 700 " .. tmpdir)
end

-- unique temp filename per request. `salt` is an opaque unique-ish extra
-- (normally the call_id) that additionally separates concurrent calls.
function unique_id(salt)
    _seq = _seq + 1
    local s = (salt and salt ~= "" and "_" .. salt) or ""
    return tostring(os.time()) .. "_" .. tostring(_seq) .. "_"
        .. tostring(math.random(1000000, 9999999)) .. s
end

-- Put the bearer header in a mode-0600 temp file. Passing a secret in curl's
-- argv would expose it to local process listings during every request.
function auth_header_file(salt)
    if api_token == "" then return nil end
    local path = tmpdir .. "/auth_" .. unique_id(salt) .. ".txt"
    local f = io.open(path, "wb")
    if not f then return nil end
    f:write("Authorization: Bearer " .. api_token .. "\n")
    f:close()
    os.execute("chmod 600 " .. string.format("%q", path))
    return path
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
    os.execute("chmod 600 " .. string.format("%q", bodyf))
    local authf = auth_header_file(salt)
    local autharg = authf and (" -H @" .. string.format("%q", authf)) or ""
    local cmd = string.format(
        "curl -s -m 300 -X POST 'http://%s:%s%s' -H 'Content-Type: application/json'%s -d %s -o %s",
        agent_host, agent_port, path, autharg,
        "@" .. string.format("%q", bodyf), string.format("%q", fn))
    os.execute(cmd)
    os.remove(bodyf)
    if authf then os.remove(authf) end
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

-- SHELL SAFETY: call_id is interpolated into curl URLs, file names and
-- mkdir/rm -rf lines below. The agent answers [0-9a-f]+; accept nothing
-- else so a compromised/odd response can never inject shell metachars.
function safe_id(s)
    if type(s) ~= "string" then return nil end
    if string.match(s, "^[%w%-_]+$") then return s end
    return nil
end

-- Fallback only when POST /calls omits greeting. Prefer API greeting
-- (conversation_system rotates GREETING_POOL per call).
local GREETING_TEXT =
    "Здравствуйте! Это Вера из Имвера. Как вы себя чувствуете?"

function get_greeting(call_id, greeting_text)
    local text = greeting_text
    if not text or text == "" then
        text = GREETING_TEXT
    end
    local body = string.format([=[{"text": %q}]=], text)
    local data = http_post("/say", body, call_id)
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

-- Instant backchannel while STT runs (3–4 s); avoids dead air after user speaks.
function play_random_ack()
    local acks = {}
    local p = io.popen("ls " .. tmpdir .. "/acks/ack-*.wav 2>/dev/null")
    for f in p:lines() do table.insert(acks, f) end
    p:close()
    if #acks > 0 then
        math.randomseed(os.time())
        play_wav(acks[math.random(#acks)])
    end
end

-- Streaming turn: POST /turn_stream in the BACKGROUND, then poll the
-- segment directory and play each finished sentence the moment it lands.
-- First audio starts while the LLM is still generating the rest.
--
-- STEP 3 (CONTINUOUS AUDIO): `chunks` is a TABLE of recorded WAV paths, not
-- a single pre-merged file. The agent server already concatenates
-- {"audio": [chunk1, chunk2, ...]} itself (save_upload), so Lua no longer
-- writes an intermediate turn-merge on disk — one fewer stale WAV in the
-- hot path and no double concat.
function do_turn_stream(call_id, chunks, segdir)
    local bodyf = tmpdir .. "/body_" .. unique_id(call_id) .. ".json"
    local bf = io.open(bodyf, "wb")
    if not bf then return nil end
    -- Build the JSON "audio":[list] array by hand (no cjson dependency).
    local arr = {}
    for _, cw in ipairs(chunks or {}) do
        table.insert(arr, string.format("%q", cw))
    end
    local audio_json = "[" .. table.concat(arr, ", ") .. "]"
    bf:write("{\"audio\": " .. audio_json ..
             ", \"segment_dir\": " .. string.format("%q", segdir) .. "}")
    bf:close()
    os.execute("chmod 600 " .. string.format("%q", bodyf))
    local authf = auth_header_file(call_id)
    local autharg = authf and (" -H @" .. string.format("%q", authf)) or ""
    local respf = tmpdir .. "/resp_" .. unique_id(call_id) .. ".json"
    local cmd = string.format(
        "curl -s -m 300 -X POST 'http://%s:%s/calls/%s/turn_stream' " ..
        "-H 'Content-Type: application/json'%s -d @'%s' -o '%s' &",
        agent_host, agent_port, call_id, autharg, bodyf, respf)
    os.execute(cmd)

    -- poll & play: seg-NNNN.wav appears atomically (tmp -> rename)
    local n = 0
    local deadline = os.time() + 90
    -- WALL-CLOCK FIX: os.clock() is CPU time of this process; the poll loop
    -- spends its life blocked in io/os.execute, so CPU seconds accumulate
    -- orders of magnitude slower than wall time and the ack never fired.
    -- Count actual 0.1 s sleeps instead: 12 x 0.1 ~= the intended ~1.2 s.
    local waits = 0
    local ack_played = false
    while os.time() < deadline do
        if not session:ready() then break end
        local next_seg = segdir .. string.format("/seg-%04d.wav", n + 1)
        local fh = io.open(next_seg, "rb")
        if fh then
            fh:close()
            n = n + 1
            play_wav(next_seg)
        else
            -- Backchannel: after ~0.8 s without first segment, play ONE ack.
            if not ack_played and waits >= 8 then
                ack_played = true
                local acks = {}
                local p = io.popen("ls " .. tmpdir .. "/acks/ack-*.wav 2>/dev/null")
                for f in p:lines() do table.insert(acks, f) end
                p:close()
                if #acks > 0 then
                    math.randomseed(os.time())
                    play_wav(acks[math.random(#acks)])
                end
            end
            local df = io.open(segdir .. "/done.json", "rb")
            if df then
                df:close()
                break
            end
            os.execute("sleep 0.1")
            waits = waits + 1
        end
    end
    os.remove(bodyf)
    if authf then os.remove(authf) end
    os.remove(respf)

    -- final flags: finished -> the call ends after this turn
    local finished = false
    local df = io.open(segdir .. "/done.json", "rb")
    if df then
        local data = df:read("*a")
        df:close()
        finished = (json_get(data, "finished") == "true")
    end
    return finished
end

function main()
    mkdirs()
    local ok, err = pcall(function() session:answer() end)
    if not ok then
        return
    end

    -- create an isolated session for THIS call (check_in arms the wellness
    -- agenda; caller_id enables family questions when registered).
    local caller = session:getVariable("caller_id_number") or ""
    local body = [[{"mode":"check_in"}]]
    if caller ~= "" then
        body = string.format([[{"mode":"check_in","caller_id":%q}]], caller)
    end
    local data = http_post("/calls", body, "")
    local call_id = safe_id(json_get(data, "call_id"))
    if not call_id or call_id == "" then
        return
    end

    local turn_files = {}
    local finished_cleanly = false

    -- NOTE 2026-08-23: RECORD_STEREO experiments reverted. Lowercase
    -- "record_stereo" made the record app write EMPTY files (44-byte
    -- headers -> "she can't hear me"), uppercase is silently ignored by
    -- this FS build (chunks stay mono). Recording must stay MONO mixed;
    -- Vera's playback echo in the user track is handled server-side by
    -- the echo-guard in orchestrator (transcript ~ her last reply ->
    -- dropped). Do NOT set any record_stereo var here without a live
    -- loopback verification of chunk sizes FIRST.

    play_wav(get_greeting(call_id, json_get(data, "greeting")))

-- Max call duration / idle guards (Phase 6 — replaces hard 6-turn cap).
local MAX_CALL_SEC = tonumber(os.getenv("MOSS_CALL_MAX_SEC") or "1200") or 1200
local MAX_IDLE_TURNS = tonumber(os.getenv("MOSS_CALL_MAX_IDLE") or "4") or 4
local ACK_WAIT_MIN = 7   -- ~0.7 s (7 x 0.1 s poll)
local ACK_WAIT_MAX = 9   -- ~0.9 s

    local call_start = os.time()
    local idle_turns = 0
    local turn_num = 0

    while session:ready() do
        if os.time() - call_start > MAX_CALL_SEC then
            session:consoleLog("info", "moss_agent: max call duration reached\n")
            break
        end
        turn_num = turn_num + 1
        if not session:ready() then
            break
        end
        -- CHUNKED RECORDING with software endpointing:
        --  * quiet room: chunk 1 ends via the FS silence detector (1 s of
        --    silence) -> turn over, fast path identical to before;
        --  * noisy room (TV/music): the detector never fires, so after each
        --    CAPPED chunk we ask the agent /has_speech (whisper VAD gate):
        --    no caller speech in the chunk -> turn over. Bounds the noise
        --    latency at ~5 s instead of dragging the full cap.
        local chunks = {}
        local turn_done = false
        for ci = 1, 3 do
            if not session:ready() then break end
            local cw = tmpdir .. "/chunk_" .. call_id .. "_" ..
                       tostring(turn_num) .. "_" .. tostring(ci) .. ".wav"
            local cap = (ci == 1) and "4 15 2" or "2 15 2"
            local cap_s = (ci == 1) and 4 or 2
            local rok = pcall(function()
                session:execute("record", cw .. " " .. cap)
            end)
            if not rok or not session:ready() then break end
            table.insert(chunks, cw)
            -- did the chunk end early via silence detection? -> turn over
            local fh = io.open(cw, "rb")
            if fh then
                local size = fh:seek("end")
                fh:close()
                local dur = (size - 44) / 16000.0   -- 8 kHz mono 16-bit
                if dur < cap_s - 0.4 then
                    turn_done = true
                    break
                end
            end
            -- chunk hit its cap: does it contain caller speech?
            local body = string.format([[{"audio": %q}]], cw)
            local rdata = http_post("/calls/" .. call_id .. "/has_speech",
                                    body, call_id)
            if json_get(rdata, "speech") ~= "true" then
                turn_done = true
                break
            end
        end
        if not session:ready() then break end
        -- STEP 3: pass the raw chunk list to the server — it concatenates
        -- {"audio":[...]}. No intermediate turn-merge WAV on disk; the
        -- server-side concat keeps one authoritative copy.
        if #chunks == 0 then
            break
        end
        for _, cw in ipairs(chunks) do
            table.insert(turn_files, cw)
        end
        -- STREAMING turn: play each sentence as soon as it is synthesized.
        local segdir = tmpdir .. "/segs_" .. call_id .. "_" ..
                       tostring(turn_num) .. "_" .. tostring(os.time())
        -- call_id is validated by safe_id, quotes are pure defense-in-depth
        os.execute("mkdir -p '" .. segdir .. "'")
        -- Backchannel only inside do_turn_stream after soft-timeout if no audio.
        local finished = do_turn_stream(call_id, chunks, segdir)
        table.insert(turn_files, segdir)
        if finished then
            finished_cleanly = true
            break
        end
        if turn_done and #chunks == 0 then
            idle_turns = idle_turns + 1
            if idle_turns >= MAX_IDLE_TURNS then
                session:consoleLog("info", "moss_agent: idle turn limit reached\n")
                break
            end
        else
            idle_turns = 0
        end
    end

    -- AUDIT FIX: always finalize the call and clean up temp WAVs, even when
    -- the loop was broken by a mid-call hangup. The agent keeps the session
    -- context for an hour otherwise, leaking memory with the wrong verdict.
    http_post("/calls/" .. call_id .. "/end", [[{}]], call_id)
    for _, f in ipairs(turn_files) do
        if string.sub(f, -4) == ".wav" then
            os.remove(f)
        else
            os.execute("rm -rf '" .. f .. "'")
        end
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
