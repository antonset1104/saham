import { Container, ContainerProxy, getContainer } from "@cloudflare/containers";
import { handleState } from "./state";

export { ContainerProxy };

type OptionalSecret =
  | "STOCKBIT_TOKEN" | "GEMINI_API_KEY" | "GROQ_API_KEY"
  | "OPENROUTER_API_KEY" | "TELEGRAM_BOT_TOKEN" | "TELEGRAM_CHAT_ID";
type ContainerEnv = Env & Partial<Record<OptionalSecret, string>>;

export class SahamContainer extends Container<ContainerEnv> {
  defaultPort = 8501;
  requiredPorts = [8501, 8503];
  sleepAfter = "15m";
  envVars = {
    SAHAM_CLOUD_MODE: "1",
    STOCKBIT_TOKEN: this.env.STOCKBIT_TOKEN ?? "",
    GEMINI_API_KEY: this.env.GEMINI_API_KEY ?? "",
    GROQ_API_KEY: this.env.GROQ_API_KEY ?? "",
    OPENROUTER_API_KEY: this.env.OPENROUTER_API_KEY ?? "",
    TELEGRAM_BOT_TOKEN: this.env.TELEGRAM_BOT_TOKEN ?? "",
    TELEGRAM_CHAT_ID: this.env.TELEGRAM_CHAT_ID ?? "",
  };

  private async ensureReady(): Promise<void> {
    await this.startAndWaitForPorts({
      ports: this.requiredPorts,
      cancellationOptions: { portReadyTimeoutMS: 120_000 },
    });
  }

  override async fetch(request: Request): Promise<Response> {
    await this.ensureReady();
    return super.fetch(request);
  }

  async runEod(): Promise<void> {
    await this.ensureReady();
    const response = await this.containerFetch("http://localhost/run/eod", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }, 8503);
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 1000);
      throw new Error(`EOD container failed: ${response.status}: ${detail}`);
    }
  }

  async runAfternoonJob(job: "refresh" | "alert"): Promise<void> {
    await this.ensureReady();
    const response = await this.containerFetch(`http://localhost/run/afternoon/${job}`, {
      method: "POST",
    }, 8503);
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 1000);
      throw new Error(`Afternoon ${job} failed: ${response.status}: ${detail}`);
    }
  }

  async runMorningAlert(): Promise<void> {
    await this.ensureReady();
    const response = await this.containerFetch("http://localhost/run/morning/alert", {
      method: "POST",
    }, 8503);
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 1000);
      throw new Error(`Morning alert failed: ${response.status}: ${detail}`);
    }
  }
}

SahamContainer.outboundByHost = {
  "state.internal": (request: Request, env: Env): Promise<Response> => handleState(request, env),
};

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (!ctx.access) return new Response("Cloudflare Access required", { status: 403 });
    const url = new URL(request.url);
    if (url.hostname !== "saham.vijeron.com") return new Response("Not found", { status: 404 });
    return getContainer(env.SAHAM_CONTAINER, "saham-main").fetch(request);
  },
  async scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const container = getContainer(env.SAHAM_CONTAINER, "saham-main");
    if (event.cron === "0,5,10,15 3 * * MON-FRI") {
      ctx.waitUntil(container.runMorningAlert());
    } else if (event.cron === "10,25 8 * * MON-FRI") {
      ctx.waitUntil(container.runAfternoonJob("refresh"));
    } else if (event.cron === "30,35,40,45 8 * * MON-FRI") {
      ctx.waitUntil(container.runAfternoonJob("alert"));
    } else if (event.cron === "30 11 * * MON-FRI") {
      ctx.waitUntil(container.runEod());
    } else {
      console.error("Unknown scheduled trigger", event.cron);
    }
  },
} satisfies ExportedHandler<Env>;
