import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { FlatList, StyleSheet, TextInput, View } from "react-native";
import { AppHeader } from "@/features/money/AppHeader";
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
import { useKeyboardInset } from "@/lib/useKeyboardInset";
import { colors, radius, space, type } from "@/theme/tokens";
import { Chip, IconButton, Screen, Text } from "@/ui";

const SUGGESTIONS = ["How much did I spend this month?", "What are my biggest subscriptions?", "Am I on track for my goals?"];

export default function ChatScreen() {
  const chat = useChat();
  const [draft, setDraft] = useState("");
  const list = useRef<FlatList<ChatItem>>(null);
  const body = useRef<View>(null);
  const keyboardInset = useKeyboardInset(body);

  // The history sheet hands back a conversation (or "new") through the route.
  const { conversation } = useLocalSearchParams<{ conversation?: string }>();
  const { open, startNew } = chat;
  useEffect(() => {
    if (!conversation) return;
    if (conversation === "new") startNew();
    else open(conversation);
    router.setParams({ conversation: undefined });
  }, [conversation, open, startNew]);

  function submit(text = draft) {
    if (!text.trim()) return;
    chat.send(text);
    setDraft("");
  }

  return (
    <Screen padded={false}>
      {/* A new chat starts from the history sheet's "New chat" row. */}
      <AppHeader leading={<IconButton icon="menu" label="Chat history" onPress={() => router.push("/history")} />} />
      <View ref={body} style={[styles.fill, { paddingBottom: keyboardInset }]}>
        <FlatList
          ref={list}
          data={chat.items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.messages}
          keyboardDismissMode="interactive"
          onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
          renderItem={({ item, index }) => (
            <Message item={item} isLast={index === chat.items.length - 1} onChoose={submit} disabled={chat.isSending} />
          )}
          ListEmptyComponent={<EmptyChat onPick={submit} />}
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
      {parts.links && parts.links.length > 0 && <ViewLinks links={parts.links} />}
      {isLast && breakdownQuery && !linksToCashFlow && <OpenInCashFlow />}
      {item.goalProposal && <GoalProposalCard proposal={item.goalProposal} />}
      {parts.action_proposal && <ActionProposalCard proposal={parts.action_proposal} />}
    </View>
  );
}

function EmptyChat({ onPick }: { onPick: (text: string) => void }) {
  return (
    <View style={styles.empty}>
      <Text variant="title">Ask your money anything.</Text>
      <View style={styles.chips}>
        {SUGGESTIONS.map((s) => (
          <Chip key={s} label={s} onPress={() => onPick(s)} />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
  empty: { flex: 1, justifyContent: "center", gap: space.lg },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: space.sm,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderTopColor: colors.line,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  input: {
    ...type.body,
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    color: colors.ink,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radius.md,
    paddingHorizontal: space.md + 2,
    paddingTop: space.md - 1,
    paddingBottom: space.md - 1,
  },
});
