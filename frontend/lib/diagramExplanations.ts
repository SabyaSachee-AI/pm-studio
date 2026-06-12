const DIAGRAM_INTROS: Record<string, string> = {
  deployment:
    "This deployment diagram shows how the Smart Note Taker application is hosted on AWS — from the user browser through CDN, frontend, API, data stores, object storage, and background workers.",
  system_overview:
    "This system overview shows the main runtime components and how requests, data, and async jobs move between the browser, API tier, PostgreSQL, Redis, Celery queue, and worker processes.",
  request_lifecycle:
    "This sequence diagram explains the record-and-retrieve lifecycle step by step — note upload, async transcription, database updates, and cached reads.",
  erd: "This entity-relationship diagram documents the core database tables, primary keys, and relationships.",
  component_tree:
    "This component tree shows how the frontend application is organized into layouts, routes, and reusable UI modules.",
  routing: "This routing diagram maps URL paths to frontend pages and navigation flow.",
  auth_flow: "This diagram explains how users authenticate and how tokens or sessions are validated on each request.",
  rbac_flow:
    "This diagram shows how role-based access control checks are applied before protected actions run.",
  user_flow: "This user-flow diagram walks through the primary screens and decisions a user takes in the product.",
  page_layout:
    "This layout diagram shows the main regions of the primary UI screen (header, navigation, content, actions).",
};

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function extractParticipantMap(chart: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const line of chart.split("\n")) {
    const quoted = line.match(/^\s*participant\s+(\S+)\s+as\s+"([^"]+)"/i);
    if (quoted) {
      map.set(quoted[1], quoted[2]);
      continue;
    }
    const plain = line.match(/^\s*participant\s+(\S+)\s+as\s+(\S+)/i);
    if (plain) map.set(plain[1], plain[2]);
  }
  return map;
}

function resolveNode(id: string, labels: Map<string, string>): string {
  return labels.get(id) ?? id;
}

function extractNodeLabels(chart: string): Map<string, string> {
  const map = new Map<string, string>();
  const patterns = [
    /(\w+)\["([^"]+)"\]/g,
    /(\w+)\[\("([^"]+)"\)\]/g,
    /(\w+)\[([^\]"{}|()]+)\]/g,
  ];
  for (const pattern of patterns) {
    for (const match of chart.matchAll(pattern)) {
      map.set(match[1], match[2].trim());
    }
  }
  return map;
}

function explainSequence(chart: string): string[] {
  const participants = extractParticipantMap(chart);
  const steps: string[] = [];

  for (const line of chart.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || /^sequenceDiagram/i.test(trimmed) || /^participant/i.test(trimmed)) {
      continue;
    }

    const arrow = trimmed.match(
      /^(\w+)\s*(-?>|--+>)\s*(\w+)\s*:\s*(.+)$/,
    );
    if (!arrow) continue;

    const from = resolveNode(arrow[1], participants);
    const to = resolveNode(arrow[3], participants);
    const message = arrow[4].trim();
    const isReturn = arrow[2].includes("--");

    steps.push(
      isReturn
        ? `${to} responds to ${from}: ${message}.`
        : `${from} calls ${to}: ${message}.`,
    );
  }

  return steps;
}

function explainFlowchart(chart: string): string[] {
  const labels = extractNodeLabels(chart);
  const steps: string[] = [];

  for (const line of chart.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const subgraph = trimmed.match(/^subgraph\s+\S+\s*\["([^"]+)"\]/i);
    if (subgraph) {
      steps.push(`Components are grouped under “${subgraph[1]}”.`);
      continue;
    }

    const arrow = trimmed.match(/^(\w+)\s*-+>\s*(\w+)/);
    if (arrow) {
      const from = resolveNode(arrow[1], labels);
      const to = resolveNode(arrow[2], labels);
      steps.push(`${from} connects to ${to}.`);
    }
  }

  return steps;
}

function explainEr(chart: string): string[] {
  const steps: string[] = [];
  for (const line of chart.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || /^erDiagram/i.test(trimmed)) continue;
    if (/[|}o.{]+[-]+[|}o.{]+/i.test(trimmed)) {
      steps.push(`Relationship: ${trimmed.replace(/\s+/g, " ")}.`);
    }
  }
  return steps;
}

/** Build a step-by-step explanation paragraph for a diagram page in the PDF. */
export function buildDiagramExplanation(
  name: string,
  chart: string,
  doc?: Record<string, unknown>,
): string {
  const intro =
    DIAGRAM_INTROS[name] ??
    `This ${humanize(name)} diagram summarizes part of the technical design for this section.`;

  let steps: string[] = [];
  if (/^sequenceDiagram/im.test(chart)) {
    steps = explainSequence(chart);
  } else if (/^flowchart|^graph/im.test(chart)) {
    steps = explainFlowchart(chart);
  } else if (/^erDiagram/im.test(chart)) {
    steps = explainEr(chart);
  }

  if (name === "system_overview" && Array.isArray(doc?.data_flow)) {
    const flow = (doc.data_flow as string[]).slice(0, 6);
    if (flow.length > 0 && steps.length < 4) {
      steps = flow.map((item, i) => `Data flow ${i + 1}: ${item.replace(/\.$/, "")}.`);
    }
  }

  if (steps.length === 0) {
    return intro;
  }

  const capped = steps.slice(0, 14);
  const numbered = capped.map((step, i) => `Step ${i + 1}. ${step}`).join("\n");
  const suffix =
    steps.length > capped.length
      ? `\n…and ${steps.length - capped.length} more connection(s) shown in the diagram.`
      : "";

  return `${intro}\n\n${numbered}${suffix}`;
}

function uniqueList(items: string[], max = 8): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const key = item.toLowerCase();
    if (!item.trim() || seen.has(key)) continue;
    seen.add(key);
    out.push(item);
    if (out.length >= max) break;
  }
  return out;
}

function collectDiagramActors(chart: string): string[] {
  if (/^sequenceDiagram/im.test(chart)) {
    const participants = extractParticipantMap(chart);
    return uniqueList([...participants.values()]);
  }
  return uniqueList([...extractNodeLabels(chart).values()]);
}

function joinNatural(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function componentNames(doc?: Record<string, unknown>): string[] {
  const rows = (doc?.components as Array<Record<string, unknown>>) ?? [];
  return uniqueList(rows.map((c) => String(c.name ?? "")).filter(Boolean));
}

function infrastructureProvider(doc?: Record<string, unknown>): string {
  const infra = doc?.infrastructure as Record<string, unknown> | undefined;
  const hosting = infra?.hosting as Record<string, unknown> | undefined;
  return String(hosting?.provider ?? "cloud infrastructure");
}

const STORY_PURPOSE: Record<string, string> = {
  deployment:
    "The deployment view tells the operations and engineering teams where each service runs in production and how traffic reaches it.",
  system_overview:
    "The system overview gives architects and backend engineers a single map of runtime dependencies before they design features or debug incidents.",
  request_lifecycle:
    "The request lifecycle shows developers exactly how a user action travels through synchronous API work and asynchronous background processing.",
  erd: "The data model diagram helps backend engineers and DBAs agree on entities, ownership, and migration order before writing queries.",
  component_tree:
    "The component tree guides frontend developers when placing new screens, shared widgets, and state boundaries.",
  routing:
    "The routing map helps frontend and QA teams trace URLs to screens and verify navigation during releases.",
  auth_flow:
    "The authentication flow clarifies how credentials are issued, validated, and renewed so security reviews stay consistent.",
  rbac_flow:
    "The RBAC flow documents who may perform protected actions and where authorization is enforced in the stack.",
  user_flow:
    "The user-flow diagram aligns product, design, and engineering on the intended journey through the application.",
  page_layout:
    "The page layout shows where primary content, navigation, and actions live so UI changes stay consistent.",
};

/**
 * Narrative paragraph(s) for the portrait page after each diagram —
 * purpose, usage, benefits, and dependencies in plain language.
 */
export function buildDiagramStory(
  name: string,
  chart: string,
  doc?: Record<string, unknown>,
): string {
  const title = humanize(name);
  const actors = collectDiagramActors(chart);
  const actorText = joinNatural(actors);
  const purpose =
    STORY_PURPOSE[name] ??
    `This ${title.toLowerCase()} diagram documents an important part of the architecture for reviewers, implementers, and operations.`;

  const paragraphs: string[] = [];

  paragraphs.push(purpose);

  if (actorText) {
    paragraphs.push(
      `In practice, the diagram centres on ${actorText}. These elements are the building blocks the team references when estimating work, planning integrations, and tracing failures across environments.`,
    );
  }

  if (name === "deployment") {
    const provider = infrastructureProvider(doc);
    paragraphs.push(
      `Why we use it: hosting on ${provider} separates edge delivery, application compute, managed databases, cache, object storage, and worker tiers so each layer can scale independently. Operations uses this view for provisioning, firewall rules, secrets, and disaster-recovery planning. Developers use it to know which service owns persistence, which handles async jobs, and where external AI APIs are called.`,
    );
    paragraphs.push(
      `How it helps: when latency rises or a worker queue backs up, the team can follow the arrows from browser → CDN → frontend → API → queue → workers → storage without guessing hidden dependencies. The main dependencies are the frontend’s reliance on the API, the API’s reliance on PostgreSQL and Redis, and workers’ reliance on object storage plus external transcription/NLP providers.`,
    );
  } else if (name === "system_overview") {
    const components = componentNames(doc);
    const pattern = String(doc?.architecture_pattern ?? "modular architecture");
    paragraphs.push(
      `Why we use it: Smart Note Taker follows a ${pattern.toLowerCase()} so product features (transcription, categorization, search, sync) can evolve without rewriting the entire stack. This overview is the map new engineers study on day one.`,
    );
    if (components.length > 0) {
      paragraphs.push(
        `The documented components — ${joinNatural(components)} — show clear responsibilities. The API remains the integration hub; PostgreSQL is the system of record; Redis accelerates reads; Celery isolates long-running transcription and NLP work from interactive requests.`,
      );
    }
    paragraphs.push(
      `How it helps: during design reviews, the team validates that every new feature declares which boxes it touches and which dependencies it introduces. During incidents, on-call engineers follow the same paths to see whether a failure is in sync API code, cache, database, or a background worker.`,
    );
  } else if (name === "request_lifecycle") {
    paragraphs.push(
      `Why we use it: note recording is not instantaneous — audio must be stored, transcribed, and written back. The sequence makes that async contract explicit so API designers keep POST endpoints fast (202 Accepted) while workers finish heavy processing.`,
    );
    paragraphs.push(
      `How it helps: frontend engineers know when to poll or listen for completion; backend engineers know when to enqueue Celery tasks; QA can script end-to-end tests that mirror each message. Dependencies include S3 for audio, external AI for transcription, PostgreSQL for durable note state, and Redis when serving cached note lists.`,
    );
  } else if (name === "erd") {
    paragraphs.push(
      `Why we use it: shared entity definitions prevent duplicate tables, orphaned foreign keys, and conflicting migrations across services. DBAs and application developers use this diagram when writing Alembic revisions and query plans.`,
    );
    paragraphs.push(
      `How it helps: it shows which records must exist before others can be created, which relationships enforce referential integrity, and where soft-delete or versioning tables (for example note versions) attach to core entities.`,
    );
  } else if (/^sequenceDiagram/im.test(chart)) {
    paragraphs.push(
      `Why we use it: sequence diagrams capture time ordering — who calls whom, when responses return, and where asynchronous hand-offs occur. That timing detail is easy to lose in prose alone.`,
    );
    paragraphs.push(
      `How it helps: during implementation, each arrow becomes an integration test or API contract check. Dependencies appear wherever a participant outside the core API appears (storage, cache, queue, or third-party AI).`,
    );
  } else if (/^flowchart|^graph/im.test(chart)) {
    paragraphs.push(
      `Why we use it: flowcharts express structure and dependency direction — which components must be available before others can function. They are ideal for onboarding, security reviews, and release checklists.`,
    );
    paragraphs.push(
      `How it helps: if any node in the path fails, the team immediately sees upstream and downstream impact. Arrows represent runtime dependencies: a broken cache still allows database fallback; a broken queue blocks async features but not read-only browsing.`,
    );
  } else if (/^erDiagram/im.test(chart)) {
    paragraphs.push(
      `How it helps: engineering uses this to align ORM models, API payloads, and migration scripts so the database remains the single source of truth for domain relationships.`,
    );
  } else {
    paragraphs.push(
      `How it helps: teams reuse this diagram in sprint planning, code reviews, and handover documents so everyone shares the same mental model of dependencies and responsibilities.`,
    );
  }

  if (Array.isArray(doc?.data_flow) && name !== "system_overview") {
    const sample = (doc.data_flow as string[])[0];
    if (sample) {
      paragraphs.push(
        `Related product flow: ${sample.replace(/\.$/, "")}. The diagram should be read together with the narrative data-flow steps in this section.`,
      );
    }
  }

  return paragraphs.join("\n\n");
}
