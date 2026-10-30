import { router } from "expo-router";
import { FlatList, StyleSheet } from "react-native";
import { fetchConversations } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";
import { useResource } from "@/lib/useResource";
import { space } from "@/theme/tokens";
import { ErrorState, ListRow, Loading, Text } from "@/ui";

/** Past conversations; picking one reopens it in the Chat tab. */
export default function HistorySheet() {
  const { status, data, error, retry } = useResource(fetchConversations);

  function pick(conversation: string) {
    router.dismissTo({ pathname: "/chat", params: { conversation } });
  }

  if (status === "loading" && !data) return <Loading />;
  if (status === "error" && !data) return <ErrorState message={error} onRetry={retry} />;
  return (
    <FlatList
      data={data ?? []}
      keyExtractor={(c) => c.conversation_id}
      ListHeaderComponent={<ListRow title="New chat" onPress={() => pick("new")} />}
      renderItem={({ item }) => (
        <ListRow
          title={item.preview}
          subtitle={`${formatRelativeTime(item.last_message_at)} · ${item.message_count} messages`}
          onPress={() => pick(item.conversation_id)}
        />
      )}
      ListEmptyComponent={
        <Text tone="soft" align="center" style={styles.empty}>
          No past conversations yet.
        </Text>
      }
    />
  );
}

const styles = StyleSheet.create({
  empty: { padding: space.xl },
});
