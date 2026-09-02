// The one place the agent install commands are written. Settings ▸ Agents lists
// every platform at once; onboarding shows one at a time. Both render from here,
// so a change to the docker flags or the installer flags can't drift between them.
import type { AgentPlatform, AgentRelease } from "../api/types";

/** Docker is offered alongside the native platforms but isn't an AgentPlatform —
 *  there is no binary to download for it, only a command. */
export type InstallTarget = AgentPlatform | "docker";

export const INSTALL_TARGETS: { k: InstallTarget; label: string }[] = [
  { k: "docker", label: "Docker" },
  { k: "linux", label: "Linux" },
  { k: "macos", label: "macOS" },
  { k: "windows", label: "Windows" },
];

export const DEFAULT_DOCKER_IMAGE = "ghcr.io/cherubyte/cherubyte-agent:latest";

/** The command to paste on the machine the agent will run on. `heading` is the
 *  already-translated comment line; docker has none. */
export function installCommand(
  target: InstallTarget,
  opts: { panelUrl: string; token: string; heading?: string; dockerImage?: string },
): string {
  const { panelUrl, token, heading = "", dockerImage } = opts;

  if (target === "docker")
    return `docker run -d --name cherubyte-agent --network host \\
  --cap-add NET_RAW --cap-add NET_ADMIN \\
  -v cherubyte-agent:/var/lib/cherubyte-agent \\
  -e CHERUBYTE_AGENT_PANEL_URL=${panelUrl} \\
  -e CHERUBYTE_AGENT_ENROL_TOKEN=${token} \\
  ${dockerImage ?? DEFAULT_DOCKER_IMAGE}`;

  if (target === "windows")
    return `# ${heading}  (elevated PowerShell)
curl.exe -fsSL ${panelUrl}/api/agents/download/windows -o cherubyte-agent.exe
curl.exe -fsSL ${panelUrl}/api/agents/installer/windows -o install.ps1
.\\install.ps1 -PanelUrl ${panelUrl} -EnrolToken ${token} -ExePath .\\cherubyte-agent.exe`;

  return `# ${heading}
curl -fsSL ${panelUrl}/api/agents/download/${target} -o cherubyte-agent && chmod +x cherubyte-agent
curl -fsSL ${panelUrl}/api/agents/installer/${target} | sudo bash -s -- \\
  --panel ${panelUrl} --token ${token} --binary ./cherubyte-agent`;
}

/** Whether this panel can actually serve a binary for `target` right now.
 *  Docker never can — it pulls its own image — and a release that errored or
 *  hasn't been fetched yet offers nothing. */
export function hasDownload(target: InstallTarget, release?: AgentRelease): boolean {
  if (target === "docker" || !release || release.error) return false;
  return release.platforms.includes(target);
}
