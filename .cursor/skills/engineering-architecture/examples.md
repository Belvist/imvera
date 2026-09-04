# Engineering Architecture — MossVoice Examples

## Example 1: Scheduler Job Leasing

**Problem:** Two workers must not dial the same elder simultaneously.

**States:** `pending` → `leased` → `completed` | `failed` | `no_contact`

**Invariants:**
- At most one active lease per job.
- Lease expires without heartbeat → reclaimable.

**Solution:** `claim_jobs` uses `FOR UPDATE SKIP LOCKED`; `lease_owner` + `leased_until` on row.

**Failure modes:**
- Worker dies mid-lease → job returns to pool after TTL.
- Kill switch env → `may_originate` returns false, no dial.

---

## Example 2: Dialogue Safety Latch

**Problem:** After «голова болит» + confirm, call must not stay in safety forever on «отлично, не болело».

**States:** `SAFETY_CONFIRM`, `SAFETY_ACTIVE`, `CHECKIN`, ...

**Event flow:**
- `symptom` → enter safety path.
- `positive` with negation window → clear `uncertain_red` latch, resume `CHECKIN`.

**Anti-pattern avoided:** Boolean `_still_in_safety` patched in 6 places → replaced by FSM transitions.

---

## Example 3: Echo Guard (Mono Record Path)

**Problem:** Vera's TTS in mono mix → STT transcribes echo as user speech.

**Not a stub:** `_looks_like_echo` compares token overlap with `_last_reply`; echo → `plan_reply("", reason="echo")` — empty turn, no memory write.

**True fix (deferred per ROADMAP P4):** direction-split media via ESL — architecture documented, not faked as done.

---

## Example 4: Product API IDOR

**Pattern:** Every `household_id` route calls membership check before read/write.

```python
# Correct: verify grant, then query with household_id param
member = store.require_membership(user_id, household_id)
```

**Wrong:** Trust `household_id` from JSON body without server-side grant lookup.

---

## Example 5: Adding a New Agenda Topic

1. Add topic to `AGENDA` in `conversation/pools.py` (5+ phrase variants).
2. Add keywords to `_TOPIC_KEYS` if narrative guard needed.
3. FSM: ensure `agenda_advance` handles new index (index-guarded).
4. Test: `tests/test_task_agenda.py` + `dialog_quality.py --strict`.

Do **not** add `if topic == "new":` branch in `plan_reply` monolith.
