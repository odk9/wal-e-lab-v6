"""
ingest_discordgo.py — Extrait, normalise (Charte Wal-e), et indexe les patterns
de discordgo (bwmarrin/discordgo) dans la KB Qdrant V6.

Focus : Patterns Core pour construire des Discord bots en Go — session creation,
message handlers, slash commands, embeds, reactions, voice channels, guild members,
interactions, components, scheduled events.

Usage:
    .venv/bin/python3 ingest_discordgo.py
"""

from __future__ import annotations

import subprocess
import time
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from embedder import embed_documents_batch, embed_query
from kb_utils import build_payload, check_charte_violations, make_uuid, query_kb, audit_report

# ─── Constantes ──────────────────────────────────────────────────────────────
REPO_URL = "https://github.com/bwmarrin/discordgo.git"
REPO_NAME = "bwmarrin/discordgo"
REPO_LOCAL = "/tmp/discordgo"
LANGUAGE = "go"
FRAMEWORK = "generic"
STACK = "go+discordgo+chatbot+discord"
CHARTE_VERSION = "1.0"
TAG = "bwmarrin/discordgo"
SOURCE_REPO = "https://github.com/bwmarrin/discordgo"
DRY_RUN = False

KB_PATH = "./kb_qdrant"
COLLECTION = "patterns"


# ─── Patterns normalisés Charte Wal-e ────────────────────────────────────────
# Discordgo = Go library pour Discord API.
# Patterns CORE : bot session, message/command handlers, embeds,
# reactions, voice, interactions, guild members, components, events.
# U-5 : `handler`, `session`, `client`, `guild`, `channel`, `user` sont OK.

PATTERNS: list[dict] = [
    # ── 1. Bot Session Creation ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "os"
    "os/signal"
    "syscall"
    "github.com/bwmarrin/discordgo"
)

type XxxBot struct {
    session *discordgo.Session
}

func NewXxxBot(token string) (*XxxBot, error) {
    // Create Discord session with bot token.
    session, err := discordgo.New("Bot " + token)
    if err != nil {
        return nil, fmt.Errorf("failed to create session: %w", err)
    }

    bot := &XxxBot{session: session}

    // Register occurrence handlers.
    session.AddHandler(bot.messageCreate)
    session.AddHandler(bot.interactionCreate)

    return bot, nil
}

func (b *XxxBot) Open() error {
    return b.session.Open()
}

func (b *XxxBot) Close() error {
    return b.session.Close()
}

func main() {
    token := os.Getenv("DISCORD_TOKEN")
    bot, err := NewXxxBot(token)
    if err != nil {
        log.Fatalf("Failed to create bot: %v", err)
    }

    if err := bot.Open(); err != nil {
        log.Fatalf("Failed to open session: %v", err)
    }
    defer bot.Close()

    log.Println("Bot is running. Press Ctrl+C to exit.")
    sc := make(chan os.Signal, 1)
    signal.Notify(sc, syscall.SIGINT, syscall.SIGTERM)
    <-sc
}
""",
        "function": "bot_session_create",
        "feature_type": "model",
        "file_role": "model",
        "file_path": "examples/xxx_bot.go",
    },
    # ── 2. Message Handler ─────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) messageCreate(session *discordgo.Session, msg *discordgo.MessageCreate) {
    // Ignore dispatches from bot itself.
    if msg.Author.ID == session.State.User.ID {
        return
    }

    // Check for command prefix.
    if msg.Content == "" || msg.Content[0] != '!' {
        return
    }

    command := msg.Content[1:]
    log.Printf("Received command '%s' from %s", command, msg.Author.Username)

    // Dispatch to handler.
    switch command {
    case "hello":
        handleHelloCommand(session, msg)
    case "ping":
        handlePingCommand(session, msg)
    default:
        session.ChannelMessageSend(msg.ChannelID, "Unknown command")
    }
}

func handleHelloCommand(session *discordgo.Session, msg *discordgo.MessageCreate) {
    response := fmt.Sprintf("Hello %s!", msg.Author.Username)
    session.ChannelMessageSend(msg.ChannelID, response)
}

func handlePingCommand(session *discordgo.Session, msg *discordgo.MessageCreate) {
    session.ChannelMessageSend(msg.ChannelID, "Pong!")
}
""",
        "function": "message_handler",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_bot.go",
    },
    # ── 3. Slash Command Register ──────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) RegisterSlashCommands() error {
    commands := []*discordgo.ApplicationCommand{
        {
            Name:        "xxx_command",
            Description: "Perform xxx command operation",
            Options: []*discordgo.ApplicationCommandOption{
                {
                    Type:        discordgo.ApplicationCommandOptionString,
                    Name:        "input",
                    Description: "Input parameter for xxx command",
                    Required:    true,
                },
            },
        },
        {
            Name:        "yyy_command",
            Description: "Perform yyy command operation",
            Options: []*discordgo.ApplicationCommandOption{
                {
                    Type:        discordgo.ApplicationCommandOptionInteger,
                    Name:        "count",
                    Description: "Number of entries",
                    Required:    false,
                },
            },
        },
    }

    for _, cmd := range commands {
        _, err := b.session.ApplicationCommandCreate(b.session.State.User.ID, "", cmd)
        if err != nil {
            return fmt.Errorf("failed to register command %s: %w", cmd.Name, err)
        }
        log.Printf("Registered slash command: %s", cmd.Name)
    }

    return nil
}
""",
        "function": "slash_command_register",
        "feature_type": "config",
        "file_role": "config",
        "file_path": "examples/xxx_commands.go",
    },
    # ── 4. Slash Command Handler ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) interactionCreate(session *discordgo.Session, interaction *discordgo.InteractionCreate) {
    data := interaction.ApplicationCommandData()

    switch data.Name {
    case "xxx_command":
        handleXxxCommand(session, interaction, data)
    case "yyy_command":
        handleYyyCommand(session, interaction, data)
    }
}

func handleXxxCommand(session *discordgo.Session, interaction *discordgo.InteractionCreate, data discordgo.ApplicationCommandInteractionData) {
    input := data.Options[0].StringValue()
    log.Printf("Executing xxx_command with input: %s", input)

    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: fmt.Sprintf("Processed xxx command with input: %s", input),
        },
    }

    session.InteractionRespond(interaction.Interaction, response)
}

func handleYyyCommand(session *discordgo.Session, interaction *discordgo.InteractionCreate, data discordgo.ApplicationCommandInteractionData) {
    var count int64 = 1
    if len(data.Options) > 0 {
        count = data.Options[0].IntValue()
    }

    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: fmt.Sprintf("yyy_command executed %d times", count),
        },
    }

    session.InteractionRespond(interaction.Interaction, response)
}
""",
        "function": "slash_command_handler",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_commands.go",
    },
    # ── 5. Embed Message Send ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "image/color"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) SendXxxEmbed(channelID string) error {
    embed := &discordgo.MessageEmbed{
        Title:       "Xxx Operation Report",
        Description: "Summary of xxx operation execution",
        Color:       int(color.RGBA{R: 0, G: 122, B: 204, A: 255}.Color()),
        Fields: []*discordgo.MessageEmbedField{
            {
                Name:   "Status",
                Value:  "Success",
                Inline: true,
            },
            {
                Name:   "Entries Processed",
                Value:  "42",
                Inline: true,
            },
            {
                Name:   "Details",
                Value:  "Operation completed without errors",
                Inline: false,
            },
        },
        Footer: &discordgo.MessageEmbedFooter{
            Text: "Reported by xxx-bot",
        },
    }

    _, err := b.session.ChannelMessageSendEmbed(channelID, embed)
    return err
}

func (b *XxxBot) SendXxxEmbedWithImage(channelID, imageURL string) error {
    embed := &discordgo.MessageEmbed{
        Title: "Xxx Result with Visualization",
        Image: &discordgo.MessageEmbedImage{
            URL: imageURL,
        },
        Color: int(color.RGBA{R: 0, G: 122, B: 204, A: 255}.Color()),
    }

    _, err := b.session.ChannelMessageSendEmbed(channelID, embed)
    return err
}
""",
        "function": "embed_message_send",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/xxx_embeds.go",
    },
    # ── 6. Reaction Handler ────────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) messageReactionAdd(session *discordgo.Session, reaction *discordgo.MessageReactionAdd) {
    // Ignore reactions from bot itself.
    if reaction.UserID == session.State.User.ID {
        return
    }

    log.Printf("Reaction %s added by %s in channel %s", reaction.Emoji.Name, reaction.UserID, reaction.ChannelID)

    switch reaction.Emoji.Name {
    case "👍":
        handleUpvoteReaction(session, reaction)
    case "👎":
        handleDownvoteReaction(session, reaction)
    case "❓":
        handleQuestionReaction(session, reaction)
    }
}

func handleUpvoteReaction(session *discordgo.Session, reaction *discordgo.MessageReactionAdd) {
    notice, _ := session.ChannelMessage(reaction.ChannelID, reaction.MessageID)
    log.Printf("Notice voted up: %s", notice.Content)
}

func handleDownvoteReaction(session *discordgo.Session, reaction *discordgo.MessageReactionAdd) {
    notice, _ := session.ChannelMessage(reaction.ChannelID, reaction.MessageID)
    log.Printf("Notice voted down: %s", notice.Content)
}

func handleQuestionReaction(session *discordgo.Session, reaction *discordgo.MessageReactionAdd) {
    session.ChannelMessageSend(reaction.ChannelID, "Question marker detected. Need clarification?")
}
""",
        "function": "reaction_handler",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_reactions.go",
    },
    # ── 7. Voice Channel Join ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) JoinVoiceChannel(guildID, channelID string) (*discordgo.VoiceConnection, error) {
    // Join voice channel.
    vc, err := b.session.ChannelVoiceJoin(guildID, channelID, false, true)
    if err != nil {
        return nil, fmt.Errorf("failed to join voice channel: %w", err)
    }

    log.Printf("Joined voice channel %s in guild %s", channelID, guildID)
    return vc, nil
}

func (b *XxxBot) LeaveVoiceChannel(guildID string) error {
    vc := b.session.VoiceConnections[guildID]
    if vc == nil {
        return fmt.Errorf("not connected to any voice channel in guild %s", guildID)
    }

    return vc.Disconnect()
}

func (b *XxxBot) GetVoiceConnectionStatus(guildID string) string {
    vc := b.session.VoiceConnections[guildID]
    if vc == nil {
        return "not connected"
    }
    return "connected"
}
""",
        "function": "voice_channel_join",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/xxx_voice.go",
    },
    # ── 8. Guild Member Handler ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) memberAdd(session *discordgo.Session, member *discordgo.GuildMemberAdd) {
    log.Printf("Member %s joined guild %s", member.User.Username, member.GuildID)

    // Send welcome notice to guild.
    guild, _ := session.Guild(member.GuildID)
    welcomeMsg := fmt.Sprintf("Welcome %s to %s!", member.User.Mention(), guild.Name)
    session.ChannelMessageSend(guild.SystemChannelID, welcomeMsg)

    // Assign default role if configured.
    session.GuildMemberRoleAdd(member.GuildID, member.User.ID, "default_role_id")
}

func (b *XxxBot) memberRemove(session *discordgo.Session, member *discordgo.GuildMemberRemove) {
    log.Printf("Member %s left guild %s", member.User.Username, member.GuildID)

    guild, _ := session.Guild(member.GuildID)
    farewellMsg := fmt.Sprintf("Goodbye %s from %s", member.User.Username, guild.Name)
    session.ChannelMessageSend(guild.SystemChannelID, farewellMsg)
}

func (b *XxxBot) GetGuildMembers(guildID string) ([]*discordgo.Member, error) {
    members, err := b.session.GuildMembers(guildID, "", 1000)
    if err != nil {
        return nil, fmt.Errorf("failed to get guild members: %w", err)
    }
    return members, nil
}
""",
        "function": "guild_member_handler",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_members.go",
    },
    # ── 9. Channel Message Send ────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) SendXxxMessage(channelID string, content string) error {
    _, err := b.session.ChannelMessageSend(channelID, content)
    return err
}

func (b *XxxBot) SendXxxMessageWithMentions(channelID string, memberIDs []string) error {
    mentions := ""
    for _, uid := range memberIDs {
        mentions += fmt.Sprintf("<@%s> ", uid)
    }
    notice := fmt.Sprintf("%sOperation complete", mentions)

    _, err := b.session.ChannelMessageSend(channelID, notice)
    return err
}

func (b *XxxBot) SendXxxMessageWithComponents(channelID string) error {
    // Notice with buttons.
    notice := &discordgo.MessageSend{
        Content: "Choose an action:",
        Components: []discordgo.MessageComponent{
            discordgo.ActionsRow{
                Components: []discordgo.MessageComponent{
                    discordgo.Button{
                        Label:    "Action A",
                        Style:    discordgo.PrimaryButton,
                        CustomID: "xxx_action_a",
                    },
                    discordgo.Button{
                        Label:    "Action B",
                        Style:    discordgo.SecondaryButton,
                        CustomID: "xxx_action_b",
                    },
                },
            },
        },
    }

    _, err := b.session.ChannelMessageSendComplex(channelID, notice)
    return err
}
""",
        "function": "channel_message_send",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/xxx_messages.go",
    },
    # ── 10. Interaction Response ───────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) RespondToInteraction(session *discordgo.Session, interaction *discordgo.Interaction, content string) error {
    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: content,
        },
    }

    return session.InteractionRespond(interaction, response)
}

func (b *XxxBot) RespondToInteractionWithEmbed(session *discordgo.Session, interaction *discordgo.Interaction, embed *discordgo.MessageEmbed) error {
    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Embeds: []*discordgo.MessageEmbed{embed},
        },
    }

    return session.InteractionRespond(interaction, response)
}

func (b *XxxBot) RespondToInteractionWithModal(session *discordgo.Session, interaction *discordgo.Interaction) error {
    modal := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseModal,
        Data: &discordgo.InteractionResponseData{
            CustomID: "xxx_modal_id",
            Title:    "Xxx Form",
            Components: []discordgo.MessageComponent{
                discordgo.ActionsRow{
                    Components: []discordgo.MessageComponent{
                        discordgo.TextInput{
                            CustomID:    "xxx_input_field",
                            Label:       "Enter xxx value",
                            Style:       discordgo.TextInputShort,
                            Placeholder: "Type here...",
                            Required:    true,
                            MaxLength:   100,
                        },
                    },
                },
            },
        },
    }

    return session.InteractionRespond(interaction, modal)
}
""",
        "function": "interaction_response",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_interactions.go",
    },
    # ── 11. Component Handler ──────────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "log"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) messageComponentInteraction(session *discordgo.Session, interaction *discordgo.InteractionCreate) {
    data := interaction.MessageComponentData()
    customID := data.CustomID

    log.Printf("Component interaction: %s from member %s", customID, interaction.Member.User.Username)

    switch customID {
    case "xxx_action_a":
        handleXxxComponentActionA(session, interaction)
    case "xxx_action_b":
        handleXxxComponentActionB(session, interaction)
    case "xxx_modal_submit":
        handleXxxModalSubmit(session, interaction, data)
    }
}

func handleXxxComponentActionA(session *discordgo.Session, interaction *discordgo.InteractionCreate) {
    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: "You selected Action A",
        },
    }
    session.InteractionRespond(interaction.Interaction, response)
}

func handleXxxComponentActionB(session *discordgo.Session, interaction *discordgo.InteractionCreate) {
    response := &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: "You selected Action B",
        },
    }
    session.InteractionRespond(interaction.Interaction, response)
}

func handleXxxModalSubmit(session *discordgo.Session, interaction *discordgo.InteractionCreate, data discordgo.MessageComponentInteractionData) {
    value := data.Components[0].(discordgo.ActionsRow).Components[0].(discordgo.TextInput).Value
    session.InteractionRespond(interaction.Interaction, &discordgo.InteractionResponse{
        Type: discordgo.InteractionResponseChannelMessageWithSource,
        Data: &discordgo.InteractionResponseData{
            Content: fmt.Sprintf("Form submitted with value: %s", value),
        },
    })
}
""",
        "function": "component_handler",
        "feature_type": "route",
        "file_role": "handler",
        "file_path": "examples/xxx_components.go",
    },
    # ── 12. Scheduled Event Create ─────────────────────────────────────────────
    {
        "normalized_code": """\
package main

import (
    "fmt"
    "time"
    "github.com/bwmarrin/discordgo"
)

func (b *XxxBot) CreateXxxScheduledOccurrence(guildID, channelID, occurrenceName string) (*discordgo.GuildScheduledEvent, error) {
    now := time.Now()
    scheduledTime := now.Add(24 * time.Hour)

    occurrence := &discordgo.GuildScheduledEventParams{
        Name:               occurrenceName,
        Description:        "Xxx scheduled occurrence",
        ScheduledStartTime: &scheduledTime,
        ChannelID:          channelID,
        EntityType:         discordgo.GuildScheduledEventEntityTypeVoice,
        PrivacyLevel:       discordgo.GuildScheduledEventPrivacyLevelGuildOnly,
    }

    scheduledOccurrence, err := b.session.GuildScheduledEventCreate(guildID, occurrence)
    if err != nil {
        return nil, fmt.Errorf("failed to create scheduled occurrence: %w", err)
    }

    return scheduledOccurrence, nil
}

func (b *XxxBot) GetXxxScheduledOccurrences(guildID string) ([]*discordgo.GuildScheduledEvent, error) {
    occurrences, err := b.session.GuildScheduledEvents(guildID, true)
    if err != nil {
        return nil, fmt.Errorf("failed to get scheduled occurrences: %w", err)
    }
    return occurrences, nil
}

func (b *XxxBot) DeleteXxxScheduledOccurrence(guildID, occurrenceID string) error {
    return b.session.GuildScheduledEventDelete(guildID, occurrenceID)
}
""",
        "function": "scheduled_event_create",
        "feature_type": "utility",
        "file_role": "utility",
        "file_path": "examples/xxx_events.go",
    },
]


# ─── Audit queries ──────────────────────────────────────────────────────────
AUDIT_QUERIES = [
    "Discord bot session creation with token authentication",
    "message handler command prefix parsing",
    "slash command registration with options",
    "slash command handler interaction dispatch",
    "embed message send with fields and color",
    "reaction add handler emoji dispatch",
    "voice channel join and disconnect",
    "guild member add remove event handlers",
    "channel message send with mentions components",
    "interaction response with modal form",
    "component button handler custom ID dispatch",
    "scheduled event create list delete Discord",
]


def clone_repo() -> None:
    import os
    if os.path.isdir(REPO_LOCAL):
        return
    subprocess.run(
        ["git", "clone", REPO_URL, REPO_LOCAL, "--depth=1"],
        check=True, capture_output=True,
    )


def build_payloads() -> list[dict]:
    payloads = []
    for p in PATTERNS:
        payloads.append(
            build_payload(
                normalized_code=p["normalized_code"],
                function=p["function"],
                feature_type=p["feature_type"],
                file_role=p["file_role"],
                language=LANGUAGE,
                framework=FRAMEWORK,
                stack=STACK,
                file_path=p["file_path"],
                source_repo=SOURCE_REPO,
                tag=TAG,
                charte_version=CHARTE_VERSION,
            )
        )
    return payloads


def index_patterns(client: QdrantClient, payloads: list[dict]) -> int:
    codes = [p["normalized_code"] for p in payloads]
    vectors = embed_documents_batch(codes)
    points = []
    for vec, payload in zip(vectors, payloads):
        points.append(PointStruct(id=make_uuid(), vector=vec, payload=payload))
    client.upsert(collection_name=COLLECTION, points=points)
    return len(points)


def run_audit_queries(client: QdrantClient) -> list[dict]:
    results = []
    for q in AUDIT_QUERIES:
        vec = embed_query(q)
        hits = query_kb(client, COLLECTION, query_vector=vec, language=LANGUAGE, limit=1)
        if hits:
            hit = hits[0]
            results.append({
                "query": q,
                "function": hit.payload.get("function", "?"),
                "file_role": hit.payload.get("file_role", "?"),
                "score": hit.score,
                "code_preview": hit.payload.get("normalized_code", "")[:50],
                "norm_ok": True,
            })
        else:
            results.append({"query": q, "function": "NO_RESULT", "file_role": "?", "score": 0.0, "code_preview": "", "norm_ok": False})
    return results


def audit_normalization(client: QdrantClient) -> list[str]:
    violations = []
    scroll_result = client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))]),
        limit=100,
    )
    for point in scroll_result[0]:
        code = point.payload.get("normalized_code", "")
        fn = point.payload.get("function", "?")
        v = check_charte_violations(code, fn, language=LANGUAGE)
        violations.extend(v)
    return violations


def cleanup(client: QdrantClient) -> None:
    client.delete(
        collection_name=COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="_tag", match=MatchValue(value=TAG))])
        ),
    )


def main() -> None:
    print(f"\n{'='*60}")
    print(f"  INGESTION {REPO_NAME}")
    print(f"  Mode: {'DRY_RUN' if DRY_RUN else 'PRODUCTION'}")
    print(f"{'='*60}\n")

    client = QdrantClient(path=KB_PATH)
    count_initial = client.count(collection_name=COLLECTION).count
    print(f"  KB initial: {count_initial} points")

    clone_repo()

    payloads = build_payloads()
    print(f"  {len(PATTERNS)} patterns extraits")

    # Cleanup existing points for this tag
    cleanup(client)

    n_indexed = index_patterns(client, payloads)
    count_after = client.count(collection_name=COLLECTION).count
    print(f"  {n_indexed} patterns indexés — KB: {count_after} points")

    query_results = run_audit_queries(client)
    violations = audit_normalization(client)

    report = audit_report(
        repo_name=REPO_NAME,
        dry_run=DRY_RUN,
        count_before=count_initial,
        count_after=count_after,
        patterns_extracted=len(PATTERNS),
        patterns_indexed=n_indexed,
        query_results=query_results,
        violations=violations,
    )
    print(report)

    if DRY_RUN:
        cleanup(client)
        print("  DRY_RUN — données supprimées")


if __name__ == "__main__":
    main()
