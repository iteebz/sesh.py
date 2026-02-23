from collections import Counter
from dataclasses import dataclass, field

from sesh.discover import discover_sessions
from sesh.parse import parse_session

echo = print


@dataclass
class AnalysisResult:
    total_sessions: int = 0
    total_turns: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    total_user_chars: int = 0
    total_assistant_chars: int = 0
    turn_counts: list[int] = field(default_factory=list)
    user_msg_lengths: list[int] = field(default_factory=list)
    first_msg_lengths: list[int] = field(default_factory=list)
    opener_words: Counter[str] = field(default_factory=Counter)
    provider_turns: dict[str, list[int]] = field(default_factory=dict)


def extract_opener(content: str) -> list[str]:
    if not content:
        return []
    words = content.lower().split()[:5]
    return [w.strip(".,!?:;\"'()[]{}") for w in words if w.strip(".,!?:;\"'()[]{}")]


def percentile(data: list[int], p: float) -> int:
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def analyze_sessions(provider: str | None = None, limit: int | None = None) -> AnalysisResult:
    files = discover_sessions(provider_filter=provider)
    if limit:
        files = files[:limit]

    result = AnalysisResult()

    for f in files:
        try:
            session = parse_session(f.path, f.provider)
        except Exception:  # noqa: S112
            continue

        user_msgs = session.user_messages
        asst_msgs = session.assistant_messages

        if not user_msgs:
            continue

        result.total_sessions += 1
        result.total_user_messages += len(user_msgs)
        result.total_assistant_messages += len(asst_msgs)

        turns = len(session.messages)
        result.total_turns += turns
        result.turn_counts.append(turns)

        if f.provider not in result.provider_turns:
            result.provider_turns[f.provider] = []
        result.provider_turns[f.provider].append(turns)

        for msg in user_msgs:
            content = msg.content or ""
            length = len(content)
            result.total_user_chars += length
            result.user_msg_lengths.append(length)

        for msg in asst_msgs:
            content = msg.content or ""
            result.total_assistant_chars += len(content)

        first_content = user_msgs[0].content or ""
        result.first_msg_lengths.append(len(first_content))

        opener_words = extract_opener(first_content)
        for word in opener_words[:3]:
            result.opener_words[word] += 1

    return result


def run(provider: str | None = None, limit: int | None = None):
    echo("Analyzing sessions...")
    result = analyze_sessions(provider=provider, limit=limit)

    if result.total_sessions == 0:
        echo("No sessions to analyze")
        return

    avg_turns = result.total_turns / result.total_sessions
    avg_user_len = result.total_user_chars / max(result.total_user_messages, 1)
    avg_asst_len = result.total_assistant_chars / max(result.total_assistant_messages, 1)
    avg_first_len = sum(result.first_msg_lengths) / len(result.first_msg_lengths)

    echo()
    echo(f"Sessions analyzed: {result.total_sessions:,}")
    echo()

    echo("Turn Distribution:")
    echo(f"  Average: {avg_turns:.1f} turns/session")
    echo(f"  Median:  {percentile(result.turn_counts, 0.5)} turns")
    echo(f"  p90:     {percentile(result.turn_counts, 0.9)} turns")
    echo(f"  p99:     {percentile(result.turn_counts, 0.99)} turns")
    echo(f"  Max:     {max(result.turn_counts)} turns")

    single_turn = sum(1 for t in result.turn_counts if t <= 2)
    short = sum(1 for t in result.turn_counts if 3 <= t <= 10)
    medium = sum(1 for t in result.turn_counts if 11 <= t <= 50)
    long = sum(1 for t in result.turn_counts if t > 50)

    echo()
    echo("Session Length Categories:")
    echo(
        f"  Single-turn (1-2):  {single_turn:>5} ({100 * single_turn / result.total_sessions:.1f}%)"
    )
    echo(f"  Short (3-10):       {short:>5} ({100 * short / result.total_sessions:.1f}%)")
    echo(f"  Medium (11-50):     {medium:>5} ({100 * medium / result.total_sessions:.1f}%)")
    echo(f"  Long (50+):         {long:>5} ({100 * long / result.total_sessions:.1f}%)")

    echo()
    echo("Message Lengths:")
    echo(f"  Avg user message:     {avg_user_len:,.0f} chars")
    echo(f"  Avg assistant message:{avg_asst_len:,.0f} chars")
    echo(f"  Avg first message:    {avg_first_len:,.0f} chars")
    echo(f"  Median first message: {percentile(result.first_msg_lengths, 0.5):,} chars")
    echo(f"  p90 first message:    {percentile(result.first_msg_lengths, 0.9):,} chars")

    echo()
    echo("Top Opening Words:")
    for word, count in result.opener_words.most_common(15):
        pct = 100 * count / result.total_sessions
        echo(f"  {word:<15} {count:>5} ({pct:.1f}%)")

    if len(result.provider_turns) > 1:
        echo()
        echo("Turns by Provider:")
        for prov in sorted(result.provider_turns.keys()):
            turns = result.provider_turns[prov]
            avg = sum(turns) / len(turns)
            med = percentile(turns, 0.5)
            echo(f"  {prov:<10} avg={avg:.1f}, median={med}, n={len(turns)}")
