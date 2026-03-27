---
name: cybernetics-design-philosophy
description: >
  Cybernetics design philosophy guide based on Norbert Wiener's "The Human Use of Human Beings."
  Use this skill during: agent system design, feedback loop architecture, multi-agent orchestration,
  error handling strategy, self-correcting system design, resilience planning.
  Trigger when the user mentions "feedback loop", "self-correction", "negative feedback",
  "positive feedback", "oscillation", "homeostasis", "stability", "requisite variety",
  "entropy", "information theory", "agent orchestration", "cybernetics", or similar topics.
---

# The Human Use of Human Beings — Distilled Guide

> Source: Norbert Wiener, *The Human Use of Human Beings: Cybernetics and Society* (1950/1954)
> Central thesis: **Society can only be understood through the messages and communication facilities that belong to it. Feedback is the foundation of all purposive, self-correcting behavior.**

---

## I. Core Thesis: Communication, Control, and Feedback

Cybernetics is the science of control and communication in the animal and the machine. Its central insight: the mechanisms that allow a living organism to maintain itself against entropy are identical in structure to those that allow a machine to correct its own behavior.

**Three interlocking claims:**

1. Information is the content of what is exchanged with the outer world as we adjust to it and make our adjustment felt upon it.
2. Feedback — returning actual performance data to the control mechanism — is what distinguishes purposive behavior from mere mechanical execution.
3. Any system that cannot receive and act on feedback is an open-loop system; open-loop systems are inherently fragile in uncertain environments.

> "It is the thesis of this book that society can only be understood through a study of the messages and the communication facilities which belong to it."

---

## II. Entropy and Information: Why Systems Decay

The second law of thermodynamics describes a universe trending toward maximum disorder (heat death). Information is entropy's opponent: it is the local, temporary accumulation of order against the universal current of disorganization.

**Key principle:** Every act of verification is a local reduction of entropy. Skipping verification allows entropy to accumulate undetected.

**Practical implication:** Information degrades through every relay. A message passed through four translation steps retains a fraction of its original fidelity. This is not a failure of implementation — it is a thermodynamic law.

**Red flag:** Any system that operates without verification will degrade. Not might degrade — *will* degrade. The question is only when and how fast.

> "The machine is a device which locally and temporarily seems to resist the general tendency for the increase of entropy."

---

## III. Negative Feedback: The Foundation of Self-Correction

Negative feedback is the mechanism by which a system detects deviation from a goal and applies a corrective force proportional to that deviation. "Negative" is not a value judgment — it means the feedback opposes the direction of error.

**Structure:**

```
Reference value → [Comparator] → Error signal → [Actuator] → Output
                        ↑__________________________________|
                                Negative feedback
```

**Principle:** The feedback signal must come from an independent sensor, never from the actuator's self-report. Letting the executor evaluate its own output is equivalent to removing the comparator from the loop — the feedback circuit is physically short-circuited.

**Agent mapping:** In an AI agent system:
- Reference value = system prompt / goal definition
- Sensor = independent verification tool (compiler, grep, diff)
- Comparator = evaluation logic
- Actuator = code writer, file modifier, API caller
- Negative feedback = verify → correct → re-verify loop

An agent without a verification step is an open-loop system. It may produce correct output by chance, but it has no mechanism to detect or recover from deviation.

**Red flag:** Accepting an executor's self-report as verification. The subagent saying "task completed successfully" is not evidence of completion — it is the actuator speaking, not the sensor.

---

## IV. Positive Feedback and Oscillation: When Correction Goes Wrong

Positive feedback amplifies deviation rather than opposing it. A small error becomes a larger error, which triggers a larger correction, which overshoots, which triggers a correction in the opposite direction — the system oscillates.

Wiener describes **intention tremor**: a patient with cerebellar damage attempting to pick up a cup finds their hand oscillating violently around the cup. Each corrective movement overshoots, triggering the next overcorrection. The feedback loop is intact, but its gain is too high.

**Principle:** Every correction loop requires a convergence threshold and a maximum iteration count. An unbounded feedback loop will oscillate regardless of how carefully the individual correction steps are designed.

**Agent mapping:** The LLM hallucination spiral is a positive feedback structure:

```
Initial false assumption → generates content validating assumption →
content reinforces assumption → more confident false generation…
```

No external negative feedback (independent fact-checking) exists to oppose the amplification. The system drifts further from truth with each step.

**Red flag:** A reflection loop or retry mechanism with no termination condition. If quality scores fluctuate with each iteration rather than converging monotonically, the system is exhibiting intention tremor — investigate immediately rather than continuing to iterate.

> Intention tremor is a signal, not noise. When an agent's output quality oscillates, the cause is almost always feedback gain set too high, not insufficient effort.

---

## V. Homeostasis: How Open Systems Resist Decay

Homeostasis is the maintained stability of an open system — not a static equilibrium, but a dynamic, continuously active resistance to perturbation. The body's maintenance of temperature, blood pH, and blood sugar are all homeostatic: continuous active processes, not passive states.

**Key insight:** Stability is not the absence of disturbance — it is the continuous expenditure of energy to counter disturbance. A system that "was working yesterday" is not guaranteed to work today without the active maintenance of its feedback mechanisms.

**Principle:** Maintenance is not optional. A system that was stable at time T will degrade to instability at time T+N if its feedback loops are not actively running. One-time checks do not substitute for continuous monitoring.

**Agent mapping:**
- Continuous monitoring (health checks, log analysis, regression tests running on every change) is homeostatic behavior.
- A one-time audit before deployment is not homeostasis — it is a single measurement with no feedback loop.
- A robust agent system is one with continuous verification, not one that was verified once at launch.

> "We are not stuff that abides, but patterns that perpetuate themselves."

---

## VI. Purposive Behavior: Goal-Driven Systems

In 1943, Rosenblueth, Wiener, and Bigelow proposed a decisive thesis: purposive behavior can be completely described in terms of physical feedback mechanisms, without invoking intent, soul, or consciousness.

A guided missile tracking an aircraft and a human reaching for a cup are structurally identical: both continuously measure the deviation between current state and goal state, and both continuously generate corrective action proportional to that deviation. Purpose is not a metaphysical property — it is the external expression of a feedback loop's reference value.

**Principle:** A purposive agent measures deviation from goal rather than executing a fixed script. An agent following a script is a music box; an agent measuring deviation is a missile.

**Agent mapping:**

| Mode | Behavior | Failure Mode |
|------|----------|--------------|
| Script-driven | Executes predefined steps in order | Fails silently when any step's preconditions differ from expected |
| Goal-driven | Continuously measures distance from goal; adapts path | Can oscillate if convergence criterion is undefined |

ReAct (Reason + Act) architecture is a direct implementation of the Rosenblueth-Wiener-Bigelow framework: observe current state → compare to goal → reason about corrective action → act → observe again.

---

## VII. Requisite Variety: Controllers Must Match Environment Complexity

Ashby's Law of Requisite Variety (extended from Wiener's framework): a controller can only neutralize disturbances it has the capacity to respond to. A controller with N response modes can handle at most N classes of disturbance.

**Formal implication:** If the environment can produce M distinct failure modes and the agent has tools covering only K < M failure modes, then (M - K) failure modes will be systematically unhandled — regardless of how sophisticated the agent's reasoning is. This is not an implementation gap; it is a structural impossibility.

**Principle:** Tool diversity must match problem diversity. Giving an agent a single verification tool (e.g., only a compiler) creates guaranteed blind spots for all failure modes not detectable by that tool.

**Agent mapping:**
- Single tool for all task types → violates requisite variety
- Multi-role agent team (implementer + reviewer + security-checker) → higher variety, covers more failure modes
- Verification suite covering multiple dimensions (compilation + semantic grep + visual inspection) → requisite variety applied to the feedback loop itself

**Red flag:** Assigning one agent to handle all task types regardless of diversity. The agent's tool set defines the ceiling of problems it can solve, not its intelligence.

---

## VIII. First-Order vs. Higher-Order Feedback

Wiener distinguishes two levels of feedback:

**First-order feedback** corrects individual output deviations. A thermostat is first-order: it does not learn — it applies the same corrective response every time.

**Higher-order feedback** modifies the strategy itself. Learning is higher-order feedback: the result of an interaction does not just correct a single output, it changes the behavioral policy that generated the output. Wiener describes this as "rewriting the tape" rather than "replaying the tape."

**Principle:** The same failure mode appearing twice is a signal to change strategy, not to retry. Repeating the same approach after it has already failed once is first-order behavior applied to a higher-order problem.

**Agent mapping:**

| Level | Trigger | Agent Action |
|-------|---------|--------------|
| First-order | Single task failure | Check output, fix error, retry |
| Higher-order | Same failure mode ≥ 2 times | Reflect on strategy, change method, update plan |

Most current agent frameworks implement only first-order feedback (retry with fix). This is the cybernetic equivalent of an insect: capable of responding to known failure patterns, incapable of adapting to novel ones.

**Red flag:** A system that retries the same approach after three consecutive failures of the same type. This is not persistence — it is the absence of higher-order feedback.

---

## IX. Communication Bottlenecks: Information Degradation

> "That information may be dissipated but not gained is the cybernetic form of the second law of thermodynamics."

Every relay in a communication chain is a translation. Every translation involves selection, compression, and reencoding — operations that can only lose information, never gain it. This is not a quality-of-implementation issue; it is structural.

**Practical consequence:** In a chain of four agents where each passes its output as the next's input, the final agent may be operating on significantly degraded information — even if each individual handoff appears clean.

**Principle:** Verification must be performed at the end of the information chain, not trusted to intermediate relays. Independent validation at the endpoint is the only way to detect cumulative degradation.

**Design rules:**
- Parallel fan-out (all subagents receive complete instructions from the orchestrator) is always preferable to serial chain (each subagent receives only the previous one's output).
- Explicit intent transmission: pass not just the task description but also *why* the task is needed and *what success looks like* — intent is the first casualty of relay degradation.
- Result aggregation at the orchestrator level: subagent results must return to the orchestrator for synthesis, not be forwarded directly to the next subagent.

---

## X. Human-Machine Collaboration

Wiener's clearest practical principle: humans and machines have complementary strengths that should not be confused.

**Machines excel at:** repetitive precision execution, high-speed pattern matching across large datasets, maintaining consistent behavior under fatigue, numerical computation.

**Humans excel at:** value judgment, goal selection, handling genuinely novel situations, ethical reasoning, recognizing when a system's outputs are nonsensical.

**Principle:** Machines should handle repetitive and precise tasks; humans should handle judgment and decision. The danger is not that machines will replace human judgment — it is that humans will defer to machine outputs in domains where machine judgment is not trustworthy.

**Agent mapping (Human-in-the-loop design):**

| Decision Type | Handler |
|---------------|---------|
| Repetitive execution (format conversion, build, test) | Agent autonomous |
| Novel situation not covered by existing patterns | Human checkpoint |
| High-stakes irreversible action | Human approval required |
| Goal definition and success criteria | Human defines, agent executes |
| Ethical or value-laden tradeoffs | Human decides |

**Red flag:** Removing human checkpoints from high-stakes decision points to improve throughput. The short-term efficiency gain creates long-term fragility at exactly the points where human judgment is most valuable.

---

## XI. Agent System Mapping: Cybernetics to Modern AI

Complete correspondence table:

| Cybernetics Concept | Agent Component | Design Implication |
|---------------------|-----------------|-------------------|
| Reference value (setpoint) | System prompt / goal definition | Must be measurable; vague goals cannot be compared |
| Sensor | Tool call result, compiler output, grep result | Must be independent of executor |
| Comparator | Evaluation logic, verification step | Cannot be performed by executor |
| Actuator / Effector | Code writer, file editor, API caller | The only component allowed to act on the world |
| Negative feedback loop | Verify → correct → re-verify cycle | Every agent must have one |
| Positive feedback | Hallucination spiral, infinite retry | Must be blocked by convergence criterion |
| Homeostasis | System robustness, self-healing | Requires continuous monitoring, not one-time audit |
| Intention tremor | Reflection loop without termination | Set max iterations + convergence threshold |
| Purposive behavior | Goal-driven ReAct architecture | Measure deviation from goal, not script execution |
| Higher-order feedback | Strategy switch on repeated failure | Trigger at ≥ 2 consecutive same-type failures |
| Information degradation | Context loss in multi-hop chains | Use fan-out, not serial relay |
| Requisite variety | Tool diversity matching problem diversity | Tool set defines the ceiling of solvable problems |
| Orchestrator (control layer) | Main session / coordinator agent | Receives feedback, compares to goal, issues corrections — does not execute |
| Ant mode (rigid) | Fixed-pipeline agent | Appropriate for high-certainty, repetitive tasks only |
| Human mode (adaptive) | Open-goal agent with tool selection | Appropriate for exploratory, uncertain tasks |

---

## XII. Red Flags Quick Reference

| Signal | Meaning |
|--------|---------|
| No Feedback Agent | System runs open-loop; output quality unverified |
| Self-Report Trust | Accepting executor's own claim without independent verification |
| Infinite Correction Loop | No convergence criterion; agent oscillates indefinitely |
| Single-Tool Agent | One tool for all tasks; violates requisite variety |
| Feedback Without Memory | Same error repeated; no higher-order learning |
| Homogeneous Multi-Agent | All agents have identical roles; no diversity benefit |
| Unvalidated Delegation | Delegating without verifying delegate's output |
| Overcorrection | Each fix introduces new problems; intention tremor pattern |
| Static Goal in Dynamic Environment | Fixed objectives when context changes; no adaptation |
| Pass-Through Orchestrator | Orchestrator just forwards instructions; adds no coordination value |
| Information Loss in Chain | Multi-hop delegation with no end-to-end verification |
| Centralized Single Point | One controller bottleneck; no resilience under failure |
| Premature Optimization | Optimizing before feedback loop is stable |
| Ignoring Oscillation Signals | Score fluctuations dismissed instead of investigated |

---

## XIII. Design Principles Summary

1. Feedback is non-negotiable — every system needs a correction loop.
2. Independent verification over self-reporting.
3. Negative feedback maintains stability; positive feedback amplifies — know which you are using.
4. Set convergence thresholds — unbounded correction loops will oscillate.
5. Same failure twice means change strategy, not retry.
6. Controller variety must match environment variety (Ashby's Law).
7. Every delegation requires verification at the end of the chain.
8. Design for graceful degradation, not perfection.
9. Information decays through every relay — verify at endpoints.
10. Purposive behavior requires measuring deviation from goal, not following scripts.
11. Stable systems require continuous energy and information input — maintenance is not optional.
12. Human judgment for decisions, machine precision for execution.
13. Higher-order feedback (changing methods) is more valuable than first-order (fixing outputs).
14. Oscillation is a signal, not noise — investigate it.
15. The measure of intelligence is adaptation to change, not speed of execution.
16. Open-loop systems fail silently; closed-loop systems fail loudly and recover.
17. Entropy is the default trajectory — order requires active work.
18. The danger is not the machine; it is the concentration of control in the hands of the few who operate it.

---

## XIV. Usage Guide

Reference this guide in the following scenarios:

- **Agent architecture review**: Run through the Red Flags table (Section XII) as a design checklist. If any signal is present, address it before launch.
- **Feedback loop design**: Apply Sections III–IV–VIII. Define reference value, sensor, comparator, and actuator explicitly. Set convergence threshold before the first iteration.
- **Multi-agent orchestration**: Apply Sections VII–IX–XI. Prefer fan-out over serial chains. Ensure orchestrator aggregates results rather than forwarding them.
- **Error handling strategy**: Apply Sections III–VIII. Implement first-order feedback for known failure modes; add higher-order feedback triggers for repeated failures.
- **Resilience planning**: Apply Sections V–XII. Audit for single points of failure; convert one-time checks to continuous monitoring loops.
- **Human-in-the-loop placement**: Apply Section X. Map each decision type to the appropriate handler; never remove human checkpoints from irreversible high-stakes actions.
