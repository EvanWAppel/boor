# Friends playtest

Live app: https://web-production-0e6881.up.railway.app/

## Get Christine in

1. In the boor Clerk application, invite Christine's chosen sign-in email (the app
   restricts account creation). She follows the Clerk invitation to create her account.
2. Sign in to boor as the DM, create/open your campaign, and use **Invite player**
   with that same email. Copy the generated campaign invitation link and send it
   to Christine. Clerk account access and campaign membership are separate.
3. Christine opens the campaign link while signed in with the invited email. She
   can create her character and enter a session you've started.

## Guided introduction (Evan + Evil Evan)

1. Open a fresh active session as Evan and enter the same table as Evil Evan.
2. As the host, click **Start guided introduction**.
3. Choose a starter character on each account (or an existing owned character).
   Both accounts should appear in the lobby with their character and readiness.
   Click **I’m ready** on each. **Begin adventure** stays disabled until everyone
   is ready; changing a character makes that person not ready again. As Evan,
   click **Begin adventure**. To host without playing, choose **Join as spectator**.
   If someone is missing, the host can mark them absent; they can rejoin while
   the lobby is open. Refresh during setup to check that readiness is saved.
   With the host watching and the player not ready, check that the host sees
   who is holding up the start and the player is prompted to click **I’m ready**.
   If both accounts watch, the lobby should explain that someone must play a character.
4. As Evil Evan, choose an approach. Evan should see who is rolling and a waiting
   message. Only Evil Evan gets the roll button.
5. Roll. Both accounts should see the same die, character bonus, total, and story
   outcome. A low total still rescues the cart, with a different consequence.
6. Refresh both pages. The outcome remains, with no second roll available.
7. As Evan, click **Talk with Mara**. A low rescue roll places the conversation at
   her camp after dark; a success leaves time to reach Emberlow's gate.
8. Ask Mara a question from either playing account. Both accounts see the same
   answer, and the question becomes marked as asked. No roll is needed. Spectators
   can read but cannot ask or choose a destination.
9. Discuss the next stop in chat, then have one player choose town or river. The
   first accepted choice settles the party's destination; it cannot be overwritten
   by the other account. Refresh and verify that the answers and ending remain.
10. Continue past the destination. A **second, different check** appears for the branch
    you chose — the town path is Emberlow's gate (Persuasion/Insight); the river path is
    the old ferry landing (Perception/Stealth). Pick an approach, then have the designated
    player **Roll**. A low roll still continues the story — it only makes the fight ahead
    tougher (it must never dead-end). Both accounts see the same result.
11. Continue into a **real fight** with two enemies. Initiative and HP appear for both
    characters and both foes. On your turn you get a **Strike** button per living enemy
    (choose your target), plus **Dodge** and **Withdraw**. Enemies act automatically.
    Refresh mid-fight: HP, the turn order, and whose turn it is must remain. At zero HP
    a character sits out; the host can **Stop the fight for everyone**. No one takes
    lasting harm and campaign sheets never change — this fight is encounter-scoped.
12. After victory, defeat, withdrawal, or the round limit, click **Continue** to read the
    **recap** (what you did + where the next session begins), then **Finish the
    introduction**. Refresh to verify the saved result. Start another session to try the
    other branch. Older introductions (v1–v4) retain the ending they originally shipped with.
13. In a separate attempt, end the session during the fight. Neither account should be
    able to act or send new chat. The log stays readable.

This is the expanded ~20-minute introduction: a rescue, a conversation, a branch-specific
second check, and a real bounded fight, ending in a recap. It runs without AI calls.
Custom "try something else" approaches, pause/resume, movement, spellcasting, death saves,
and inventory are next. The host can release a pending check if its player leaves.

## Human-DM acceptance pass

- Both people can enter the same session and see each other's presence.
- Send an in-character line and an out-of-character line from each account.
- Roll a die; verify both accounts see the same result.
- DM adds two combatants and advances initiative. Player sees the change and
  cannot change initiative. Refresh either page: log and initiative recover.
- Disconnect/reconnect one device: the table reconnects and recovers missed history.
- End the session as DM; verify the campaign page reflects it.

Record any issue with the step, expected result, actual result, and approximate time.
MILE-1 remains open until this real friends session is complete.

## AI follow-up

The profile/red-line editor and per-session absence controls are available. AI
turn execution additionally requires `ENABLE_STANDINS=1` and a dedicated, capped
Anthropic workspace's `ANTHROPIC_API_KEY` on the service. Never reuse a personal
key. `STANDIN_MODEL` optionally overrides the existing model default.

1. Save the character's personality, standing instructions, risk tolerance, and
   structured red lines under **AI stand-ins → Edit personality**.
2. Owner or DM chooses **Mark absent · enable AI** for that session.
3. The DM adds scene context to the table chat and chooses **Request AI turn**.
4. Verify thinking feedback, the AI-labelled result/refusal, and character voice.
5. Choose **Take back control**. An in-flight result is discarded if control or
   the profile changed before it completes.

Current scope: one FastAPI process/replica; DM-triggered individual turns; the
scene entity roster is the campaign party. Enemy encounter authoring, automatic
combat/HP mutation, consequence-tier approval, recaps, and believability playtests
remain separate work. The existing engine still accepts model-proposed combat
modifiers; this is not a complete automated encounter runner.

## Verification on 2026-09-26

- Railway service + web builds and health checks pass after removing unsupported
  generic cache mounts and correcting public URL schemes/deploy settings.
- Live health returns 200; unauthenticated `/me` returns 401; browser preflight
  permits the web origin. Signed-out UI loads.
- Disposable local browser table: chat, dice, initiative, refresh replay, profile
  editing, stand-in handoff, scripted AI output/attribution, and control restoration.
- Scripted-model tests make no paid API calls. Real Clerk two-account playtest and
  live-model believability validation are still pending.
