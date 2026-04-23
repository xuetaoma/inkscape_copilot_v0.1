# Operation Flow

## Goal

Inkscape Copilot should feel like a simple conversational assistant for the document the user is already editing in Inkscape.

The user experience we want is:

1. Open an SVG document in Inkscape.
2. Open the copilot chat.
3. Start talking to the copilot naturally.
4. Watch the copilot understand the current document, propose or apply supported edits, and help finish the design.

Default sheet setup for local copilot assumptions:
- page width: `220 px`
- page height: `290 px`

The user should not need to think about queues, bridge files, worker lifetimes, or internal implementation details.

## Product Model

There are three product layers:

1. `Chat layer`
   The browser sidecar is the main interface.

2. `Document-awareness layer`
   The copilot needs reliable knowledge of the active document, current selection, and recent document state.

3. `Execution layer`
   The copilot turns prompts into structured actions and applies those actions to the document through a stable Inkscape-side mechanism.

## Intended User Flow

### 1. Open Document

The user opens Inkscape and opens or creates a real document window.

Important:
- The copilot should treat the real document window as the source of truth.
- The welcome screen is not a usable editing session.

### 2. Open Copilot Chat

The user clicks:

`Extensions -> Copilot -> Open Copilot Chat`

Expected behavior:
- any older copilot sidecar browser window is closed
- any older copilot web server instance is stopped
- a fresh copilot server starts
- the browser opens a fresh chat window

Important:
- opening the chat should not destroy an active document-attached session unless explicitly intended
- opening the chat should feel safe and repeatable

### 3. Attach Copilot To Document

The user clicks:

`Extensions -> Copilot -> Attach Copilot To Document`

Expected behavior:
- the current Inkscape document becomes the active document for the copilot session
- the worker records document metadata such as document name, page size, selection, and sync time
- the session stays associated with that document

Important:
- attaching the copilot should not wipe the chat state unless we intentionally want a fresh conversation
- attaching the copilot should not wipe the worker session it just created

### 4. Conversational Work

The user types into the browser chat, for example:

- `make a new square`
- `make this blue`
- `align these three objects`
- `duplicate this 5 times`

Expected behavior for each prompt:

1. refresh the current document context from Inkscape
2. build the assistant reply using the real current document context
3. create a structured action plan
4. apply supported actions to the document
5. report what happened back into the chat

Important:
- the assistant response and the action plan should be based on the same synced document context
- if the copilot cannot do something yet, it should say so clearly

### 5. Continue Iterating

The user keeps chatting while designing.

Expected behavior:
- the copilot remains conversational
- the copilot remembers recent turns
- the copilot stays aware of the currently attached document
- the user can keep typing while the copilot is thinking or applying changes

## Current Internal Model

Right now the implementation still uses bridge files, pending jobs, and short-lived Inkscape commands.

That is acceptable as an implementation detail for now, but it should not define the product.

Current internal pieces:
- browser sidecar web UI
- bridge state in the runtime directory
- short Inkscape actions such as refresh/apply/attach
- OpenAI planner and chat generation

The correct mental model is:

- user sees a document-attached assistant
- code may still use queue/bridge mechanics internally

## Target Architecture

The best architecture for this project is:

### Inkscape Side

One worker should be responsible for:

- observing the active document and writing workspace snapshots
- executing finalized action plans against the document
- reporting execution results back to the shared bridge state

The Inkscape side should be the source of truth for what the workspace currently looks like and what changes were actually applied.

### Browser Side

The browser sidecar should own:

- conversation
- reasoning
- current-step planning
- deciding when a finalized step should be applied

The browser side should first understand the workspace snapshot, then think about the user’s request, and only then decide whether to apply the current step.

### Bridge

The bridge should carry:

- the latest workspace snapshot
- the current planned step
- the current execution result

It should not be modeled primarily as “raw prompts in, immediate actions out.”

That means the bridge should evolve away from a queue-first design and toward a state-sharing design.

Instead of centering the architecture around:

- queued prompts
- queued jobs

the bridge should center around:

- latest workspace snapshot
- current planned step
- current execution result

This is much closer to a real copilot model.

## Menu Surface

The Inkscape menu should stay simple:

- `Open Copilot Chat`
- `Attach Copilot To Document`
- `Refresh Copilot Context`
- `Apply Copilot Changes`

Guidance:
- these are user-facing verbs
- names should describe what the user is trying to do, not how the implementation works

## State Responsibilities

### Browser Sidecar

Responsible for:
- showing the conversation
- showing current document/session status
- collecting prompts
- showing planning and execution feedback

Not responsible for:
- pretending it knows the document without a sync step

### Inkscape Worker

Responsible for:
- syncing real document context
- applying supported actions to the current document
- reporting session metadata and execution results

Not responsible for:
- owning the full conversational experience

### Bridge State

Responsible for:
- sharing current document context
- sharing session state
- sharing execution status between browser and Inkscape

Not responsible for:
- becoming the user-facing product model

## Design Principles

1. `Chat first`
   The chat is the primary user interface.

2. `Document attached`
   The copilot should always feel tied to the current document, not to an abstract queue.

3. `Repeatable launch`
   Opening the copilot again should be safe.

4. `Fresh sync before action`
   Before the assistant plans or acts, it should sync the real current document state.

5. `Observe, then think, then act`
   The copilot should first understand the workspace, then reason about the current step, and only then apply changes.

6. `Clear limitation handling`
   If a request is not yet supported, the copilot should say that plainly and suggest the closest supported path.

7. `Implementation detail separation`
   Internal bridge mechanics should stay behind the scenes.

## Known Prototype Gaps

These are the gaps we already know about:

1. macOS Inkscape runtime is fragile for embedded Python behaviors.
2. Menu automation is not reliable enough to be the long-term backbone.
3. The document sync/apply path still depends on short command triggers.
4. Not all desired Inkscape actions are implemented yet.
5. Some product wording still reflects the earlier queue-first prototype.

## Near-Term Execution Plan

### Phase 1: Stabilize The Current Product Flow

Focus:
- make `Open Copilot Chat` reliable
- make `Attach Copilot To Document` preserve session state
- make sync happen before assistant response and planning
- keep runtime paths dynamic instead of hardcoded

### Phase 2: Strengthen Document Attachment

Focus:
- make document attachment more explicit and reliable
- surface document name and session status clearly in the sidecar
- reduce dependence on fragile UI automation
- make the Inkscape-side worker responsible for writing durable workspace snapshots

### Phase 3: Expand Action Coverage

Focus:
- refactor the bridge around snapshots, planned steps, and execution results
- separate observe, think, and act more explicitly in the browser flow
- support more common Inkscape editing operations
- improve multi-step plans
- improve selection-aware edits and creation workflows

### Phase 4: Make The Copilot Feel Native

Focus:
- smooth live feedback
- stronger session continuity
- fewer manual “helper” steps for the user

## Definition Of Success

This project is succeeding when the user experience feels like this:

- `I open my SVG.`
- `I open Copilot Chat.`
- `I ask for what I want.`
- `The copilot helps me make the design happen.`

If the user has to think in terms of internal queues, stale sessions, extension runtime quirks, or which hidden command should run next, then the product model is still wrong.
