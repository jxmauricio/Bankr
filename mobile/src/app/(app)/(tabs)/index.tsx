import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { FlatList, StyleSheet, TextInput, View } from "react-native";
import { AssistantText } from "@/features/chat/AssistantText";
import { ChatChart } from "@/features/chat/ChatChart";
import { ActionProposalCard, GoalProposalCard } from "@/features/chat/ProposalCards";
import {
  AnswerHeadline,
  OpenInCashFlow,
  RecordCard,
  recordQuery,
  SearchedBox,
  SourceTrail,
  ViewLinks,
} from "@/features/chat/ReplyExtras";
import { useChat, type ChatItem } from "@/features/chat/useChat";
import { NetWorthCard } from "@/features/money/NetWorthCard";
import { RecapCard } from "@/features/recap/RecapCard";
import { formatTurnUsage } from "@/lib/api";
import { useKeyboardInset } from "@/lib/useKeyboardInset";
import { radius, space, type } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Chip, groupPosition, Icon, IconButton, ListRow, Screen, SectionHeader, Text } from "@/ui";

const SUGGESTIONS = ["How much did I spend this month?", "What are my biggest subscriptions?", "Am I on track for my goals?"];

export default function ChatScreen() {
  const styles = useStyles();
  const colors = useColors();
  const chat = useChat();
  const [draft, setDraft] = useState("");
  const list = useRef<FlatList<ChatItem>>(null);
  const listHeight = useRef(0);
  const body = useRef<View>(null);
  const keyboardInset = useKeyboardInset(body);

  // The history sheet hands back a conversation (or "new") through the route,
  // and the weekly recap a question to ask.
  const { conversation, ask } = useLocalSearchParams<{ conversation?: string; ask?: string }>();
  const { open, startNew, send } = chat;
  useEffect(() => {
    if (!conversation) return;
    if (conversation === "new") startNew();
    else open(conversation);
    router.setParams({ conversation: undefined });
  }, [conversation, open, startNew]);
  useEffect(() => {
    if (!ask) return;
    send(ask);
    router.setParams({ ask: undefined });
  }, [ask, send]);

  function submit(text = draft) {
    if (!text.trim()) return;
    chat.send(text);
    setDraft("");
  }

  return (
    // The tab bar above owns the top inset; chat history is in its trailing button.
    <Screen padded={false} edges={["bottom"]}>
      <View ref={body} style={[styles.fill, { paddingBottom: keyboardInset }]}>
        <FlatList
          ref={list}
          data={chat.items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messages}
          keyboardDismissMode="interactive"
          onLayout={(e) => (listHeight.current = e.nativeEvent.layout.height)}
          // Scroll by the real content height: FlatList's scrollToEnd estimates it from
          // rows it has measured, so it stops short of a reply (or chart) that just grew.
          // Not before the first message: then the growth is the dashboard (a recap card
          // arriving), which should stay in view from the top.
          onContentSizeChange={(_, height) => {
            if (chat.items.length === 0) return;
            list.current?.scrollToOffset({ offset: Math.max(0, height - listHeight.current), animated: true });
          }}
          renderItem={({ item, index }) => (
            <Message item={item} isLast={index === chat.items.length - 1} onChoose={submit} disabled={chat.isSending} />
          )}
          // The dashboard heads the conversation and scrolls away as it grows.
          ListHeaderComponent={<ChatDashboard onPick={submit} showSuggestions={chat.items.length === 0} />}
          ListFooterComponent={
            <>
              {chat.isSending && (
                <View style={styles.assistant}>
                  {chat.replySoFar ? (
                    <AssistantText text={chat.replySoFar} />
                  ) : (
                    <Text tone="soft">{chat.statusLabel || "Thinking…"}</Text>
                  )}
                </View>
              )}
              {chat.failed && (
                <View style={styles.failed}>
                  <Text variant="caption" tone="negative">
                    {chat.failed.stopped ? "Stopped." : "Bankr couldn't answer that."}
                  </Text>
                  <Chip label="Ask again" onPress={() => chat.resolveFailed("retry")} />
                  <Chip
                    label="Edit"
                    onPress={() => {
                      const text = chat.resolveFailed("edit");
                      if (text) setDraft(text);
                    }}
                  />
                </View>
              )}
            </>
          }
        />
        <View style={styles.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Ask about your money"
            placeholderTextColor={colors.inkFaint}
            style={styles.input}
            multiline
            submitBehavior="submit"
            returnKeyType="send"
            onSubmitEditing={() => submit()}
          />
          {chat.isSending ? (
            <IconButton icon="stop" label="Stop" variant="primary" onPress={chat.stop} />
          ) : (
            <IconButton icon="send" label="Send" variant="primary" onPress={() => submit()} disabled={!draft.trim()} />
          )}
        </View>
      </View>
    </Screen>
  );
}

function Message({
  item,
  isLast,
  onChoose,
  disabled,
}: {
  item: ChatItem;
  isLast: boolean;
  onChoose: (text: string) => void;
  disabled: boolean;
}) {
  const styles = useStyles();
  if (item.kind === "user") {
    return (
      <View style={styles.userBubble}>
        <Text>{item.text}</Text>
      </View>
    );
  }
  // Same pieces, in the same order, as the web app's StreamEntry.
  const { parts } = item;
  const sources = parts.sources ?? [];
  const searched = sources.filter((s) => s.searched);
  const breakdownQuery = sources.find((s) => s.query && !s.query.merchant)?.query ?? null;
  const linksToCashFlow = parts.links?.some((l) => l.view === "cash_flow") ?? false;
  const headline = parts.charts?.[0]?.headline ?? null;
  return (
    <View style={styles.assistant}>
      {headline && <AnswerHeadline headline={headline} />}
      <AssistantText text={item.text} citations={parts.citations} sources={sources} />
      {parts.records?.map((record, i) => (
        <RecordCard key={i} record={record} query={recordQuery(sources)} />
      ))}
      {searched.map((s, i) => (
        <SearchedBox key={i} source={s} />
      ))}
      {parts.clarify && isLast && (
        <View style={styles.chips}>
          {parts.clarify.choices.map((choice) => (
            <Chip key={choice.label} label={choice.label} onPress={() => onChoose(choice.label)} disabled={disabled} />
          ))}
        </View>
      )}
      {parts.charts?.map((chart, i) => (
        <ChatChart key={i} chart={chart} />
      ))}
      {sources.length > 0 && <SourceTrail sources={sources} />}
      {item.usage && (
        <Text variant="caption" tone="soft">
          {formatTurnUsage(item.usage)}
        </Text>
      )}
      {parts.links && parts.links.length > 0 && <ViewLinks links={parts.links} />}
      {isLast && breakdownQuery && !linksToCashFlow && <OpenInCashFlow />}
      {item.goalProposal && <GoalProposalCard proposal={item.goalProposal} />}
      {parts.action_proposal && <ActionProposalCard proposal={parts.action_proposal} />}
    </View>
  );
}

/** Net worth at a glance, then (before the first message) the starter questions as one grouped list. */
function ChatDashboard({ onPick, showSuggestions }: { onPick: (text: string) => void; showSuggestions: boolean }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <View style={styles.empty}>
      <View style={[styles.inset, styles.cards]}>
        <RecapCard />
        <NetWorthCard />
      </View>
      {showSuggestions && (
        <View>
          <SectionHeader title="Ask Bankr" />
          {SUGGESTIONS.map((s, i) => (
            <ListRow
              key={s}
              title={s}
              group={groupPosition(i, SUGGESTIONS.length)}
              onPress={() => onPick(s)}
              trailing={<Icon name="chevronRight" color={colors.inkFaint} size={16} />}
            />
          ))}
        </View>
      )}
    </View>
  );
}

const useStyles = makeStyles((colors) =>
  StyleSheet.create({
    fill: { flex: 1 },
    messages: { paddingHorizontal: space.lg, paddingVertical: space.xl, gap: space.lg, flexGrow: 1 },
    userBubble: {
      alignSelf: "flex-end",
      maxWidth: "80%",
      backgroundColor: colors.userBubble,
      borderTopLeftRadius: radius.lg,
      borderTopRightRadius: radius.lg,
      borderBottomLeftRadius: radius.lg,
      borderBottomRightRadius: 6,
      paddingHorizontal: space.md + 2,
      paddingVertical: space.sm + 2,
    },
    assistant: { alignSelf: "stretch", gap: space.md },
    failed: { flexDirection: "row", alignItems: "center", gap: space.md, flexWrap: "wrap" },
    // The dashboard runs edge to edge: grouped rows bring their own side margins.
    empty: { gap: space.xs, marginHorizontal: -space.lg, marginTop: -space.md },
    inset: { paddingHorizontal: space.lg },
    cards: { gap: space.md },
    chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    composer: {
      flexDirection: "row",
      alignItems: "flex-end",
      gap: space.sm,
      paddingHorizontal: space.lg,
      paddingVertical: space.sm,
    },
    input: {
      ...type.body,
      flex: 1,
      minHeight: 44,
      maxHeight: 120,
      color: colors.ink,
      backgroundColor: colors.raised,
      borderWidth: 1,
      borderColor: colors.lineStrong,
      borderRadius: 22,
      paddingHorizontal: space.lg + 2,
      paddingTop: space.md - 1,
      paddingBottom: space.md - 1,
    },
  })
);
