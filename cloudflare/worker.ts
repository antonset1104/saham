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
  async scheduled(_event: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(getContainer(env.SAHAM_CONTAINER, "saham-main").runEod());
  },
} satisfies ExportedHandler<Env>;
