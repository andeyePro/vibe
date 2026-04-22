# Vendored from anthropics/claude-code .devcontainer/Dockerfile
# Upstream commit: 0385848b4e737831fc3b973d9a78d31950a87d9d
# Fetched: 2026-04-18
# To resync: re-fetch from
#   https://raw.githubusercontent.com/anthropics/claude-code/<sha>/.devcontainer/Dockerfile
# then re-apply the vibe-specific patches (openssh-client, credential-helper).

FROM node:20

ARG TZ
ENV TZ="$TZ"

ARG CLAUDE_CODE_VERSION=latest

# Install basic development tools and iptables/ipset
RUN apt-get update && apt-get install -y --no-install-recommends \
  less \
  git \
  procps \
  sudo \
  fzf \
  zsh \
  man-db \
  unzip \
  gnupg2 \
  gh \
  iptables \
  ipset \
  iproute2 \
  dnsutils \
  aggregate \
  jq \
  nano \
  openssh-client \
  vim \
  avahi-daemon \
  avahi-utils \
  libnss-mdns \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Enable mDNS (.local resolution) — insert mdns4_minimal before dns
RUN sed -i 's/^\(hosts:.*\)dns/\1mdns4_minimal [NOTFOUND=return] dns/' /etc/nsswitch.conf

# Ensure default node user has access to /usr/local/share
RUN mkdir -p /usr/local/share/npm-global && \
  chown -R node:node /usr/local/share

ARG USERNAME=node

# Persist bash history.
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME /commandhistory

# Set `DEVCONTAINER` environment variable to help with orientation
ENV DEVCONTAINER=true

# UTF-8 locale so terminal UIs (Claude Code spinner glyphs, box-drawing) render
# correctly. node:20 inherits glibc's `C` default, which strips non-ASCII.
# C.UTF-8 is provided by glibc — no locale-gen required.
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Create workspace and config directories and set permissions
RUN mkdir -p /workspace /home/node/.claude && \
  chown -R node:node /workspace /home/node/.claude

WORKDIR /workspace

ARG GIT_DELTA_VERSION=0.18.2
RUN ARCH=$(dpkg --print-architecture) && \
  wget "https://github.com/dandavison/delta/releases/download/${GIT_DELTA_VERSION}/git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  sudo dpkg -i "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb" && \
  rm "git-delta_${GIT_DELTA_VERSION}_${ARCH}.deb"

# Set up non-root user
USER node

# Install global packages
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

# Set the default shell to zsh rather than sh
ENV SHELL=/bin/zsh

# Set the default editor and visual
ENV EDITOR=nano
ENV VISUAL=nano

# Default powerline10k theme
ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
  -p git \
  -p fzf \
  -a "source /usr/share/doc/fzf/examples/key-bindings.zsh" \
  -a "source /usr/share/doc/fzf/examples/completion.zsh" \
  -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  -x

# zsh-in-docker hardcodes en_US.UTF-8 at the top of .zshrc, which isn't
# generated in this image and clobbers the C.UTF-8 ENV above. Rewrite it so
# zsh sessions inherit the same locale as everything else.
RUN sed -i 's/en_US\.UTF-8/C.UTF-8/g; s/en_US:en/C/g' /home/node/.zshrc

# Install Claude
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}


# Copy and set up firewall script, SSH setup, env hint, and credential helper
COPY init-firewall.sh /usr/local/bin/
COPY setup-ssh.sh /usr/local/bin/
COPY setup-git.sh /usr/local/bin/
COPY write-env-hint.sh /usr/local/bin/
COPY credential-helper.sh /usr/local/bin/vibe-credential-helper
USER root
RUN chmod +x /usr/local/bin/init-firewall.sh /usr/local/bin/setup-ssh.sh /usr/local/bin/setup-git.sh /usr/local/bin/write-env-hint.sh /usr/local/bin/vibe-credential-helper && \
  echo "node ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \
  echo "node ALL=(root) NOPASSWD: /usr/sbin/avahi-daemon" >> /etc/sudoers.d/node-firewall && \
  chmod 0440 /etc/sudoers.d/node-firewall
USER node
