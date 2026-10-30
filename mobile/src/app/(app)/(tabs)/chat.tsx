import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, TextInput, View } from "react-native";
import { AssistantText } from "@/features/chat/AssistantText";
import { ChatChart } from "@/features/chat/ChatChart";
import { ActionProposalCard, GoalProposalCard } from "@/features/chat/ProposalCards";
import {
  AnswerHeadline,
  OpenInCashFlow,
  RecordCard,
  recordQuery,
  ReplyFeedback,
  SearchedBox,
  SourceTrail,
  ViewLinks,
} from "@/features/chat/ReplyExtras";
import { useChat, type ChatItem } from "@/features/chat/useChat";
import { formatTurnUsage } from "@/lib/api";
import { useKeyboardInset } from "@/lib/useKeyboardInset";
import { useFloatingTabInset } from "@/theme/tabBar";
import { radius, space, type } from "@/theme/tokens";
import { makeStyles, useColors } from "@/theme/theme";
import { Chip, groupPosition, Icon, IconButton, ListRow, Screen, SectionHeader, Text } from "@/ui";

const SUGGESTIONS = ["How much did I spend this month?", "What are my biggest subscriptions?", "Am I on track for my goals?"];
/** How far above the latest message counts as "scrolled up" enough to show jump-to-bottom. */
const AWAY_PX = 140;

export default function ChatScreen() {
  const styles = useStyles();
  const colors = useColors();
  const chat = useChat();
  const [draft, setDraft] = useState("");
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const list = useRef<FlatList<ChatItem>>(null);
  const listHeight = useRef(0);
  const contentHeight = useRef(0);
  const nearBottom = useRef(true);
  const body = useRef<View>(null);
  const keyboardInset = useKeyboardInset(body);
  const tabInset = useFloatingTabInset();

  const jumpToLatest = useCallback(() => {
    nearBottom.current = true;
    setAwayFromBottom(false);
    list.current?.scrollToOffset({ offset: Math.max(0, contentHeight.current - listHeight.current), animated: true });
  }, []);

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
    nearBottom.current = true;
    setAwayFromBottom(false);
    chat.send(text);
    setDraft("");
  }

  return (
    <Screen padded={false} edges={[]}>
      <View ref={body} style={[styles.fill, { paddingBottom: Math.max(keyboardInset, tabInset) }]}>
        <View style={styles.fill}>
          <FlatList
            ref={list}
            data={chat.items}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.messages}
            keyboardDismissMode="interactive"
            scrollEventThrottle={16}
            onLayout={(e) => (listHeight.current = e.nativeEvent.layout.height)}
            onScroll={(e) => {
              const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
              const gap = contentSize.height - layoutMeasurement.height - contentOffset.y;
              const near = gap <= AWAY_PX;
              nearBottom.current = near;
              setAwayFromBottom(!near && chat.items.length > 0);
            }}
            onContentSizeChange={(_, height) => {
              contentHeight.current = height;
              if (chat.items.length === 0 || !nearBottom.current) return;
              list.current?.scrollToOffset({ offset: Math.max(0, height - listHeight.current), animated: true });
            }}
            renderItem={({ item, index }) => (
              <Message item={item} isLast={index === chat.items.length - 1} onChoose={submit} disabled={chat.isSending} />
            )}
            ListHeaderComponent={chat.items.length === 0 ? <ChatEmpty onPick={submit} /> : null}
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
          {awayFromBottom && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Scroll to latest message"
              onPress={jumpToLatest}
              style={({ pressed }) => [styles.jump, pressed && styles.jumpPressed]}
            >
              <Icon name="chevronDown" color={colors.onAccent} size={20} />
            </Pressable>
          )}
        </View>
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
        <Text tone="onUser">{item.text}</Text>
      </View>
    );
  }
  const { parts } = item;
  const sources = parts.sources ?? [];
  const searched = sources.filter((s) => s.searched);
  const breakdownQuery = sources.find((s) => s.query && !s.query.merchant)?.query ?? null;
  const linksToCashFlow = parts.links?.some((l) => l.view === "cash_flow") ?? false;
  const headline = parts.charts?.[0]?.headline ?? null;
  return (
    <View style={styles.assistant}>
      {headline && <AnswerHeadline headline={headline} />}
      <AssistantText text={item.text} citations={parts.citations} uncited={parts.uncited_figures} sources={sources} />
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
      <ReplyFeedback key={item.messageId} messageId={item.messageId} initial={item.feedback ?? null} />
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

function ChatEmpty({ onPick }: { onPick: (text: string) => void }) {
  const styles = useStyles();
  const colors = useColors();
  return (
    <View style={styles.empty}>
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
    empty: { marginHorizontal: -space.lg, marginTop: -space.md },
    chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    jump: {
      position: "absolute",
      alignSelf: "center",
      bottom: space.md,
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: colors.accent,
      shadowColor: "#12151C",
      shadowOpacity: 0.18,
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 2 },
      elevation: 3,
    },
    jumpPressed: { opacity: 0.7 },
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
