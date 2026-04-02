from dataclasses import dataclass

class CodingNode:
    def __init__(
        self,
        label: str,
        yes=None,
        no=None,
        question_text: str | None = None,
        help_text: str | None = None,
    ):
        self.label = label
        self.yes = yes
        self.no = no
        self.question_text = question_text
        self.help_text = help_text

    def is_leaf(self) -> bool:
        return self.yes is None and self.no is None

    def next_step(self, answer: bool) -> "CodingNode":
        return self.yes if answer else self.no

    def question(self) -> "QuestionStep | None":
        if self.is_leaf():
            return None

        return QuestionStep(
            code=self.label,
            text=self.question_text,
            help_text=self.help_text,
        )

    def classification_label(self) -> str:
        return CodingLabels.get(self.label, "Unknown Classification")

CodingLabels = {
    "M1a": "Unfocused",
    "M1b": "Unclear",
    "M2": "Not CI/CD security Related",
    "T": "Outcome",
    "T'": "Outcome",
    "P1": "Incompletely Specified Practice",
    "P2": "General Policy/Approach",
    "P3": "Infeasible Practice",
    "P4": "Security Expert",
    "P5": "IT Specialist",
    "P6": "Average developer",
    "N": "Security Principle",
}


@dataclass(frozen=True)
class QuestionStep:
    code: str
    text: str
    help_text: str


Q8 = CodingNode(
    label="Q8",
    no=CodingNode("P5"),
    yes=CodingNode("P4"),
    question_text="Is it intended that a security expert carry out this item?",
    help_text="Does following this advice require an expert understanding of security and security implementation in order to properly follow the advice? Someone following this advice item would have to be an expert in security to be able to understand it and successfully follow it, or be capable of extracting actionable steps from an otherwise non-actionable item based on their experience.",
)
Q7 = CodingNode(
    label="Q7",
    yes=CodingNode("P6"),
    no=Q8,
    question_text="Is it intended that the average developer carry out this item?",
    help_text="Does the item suggest that the average developer can carry out this practice?",
)
Q6 = CodingNode(
    label="Q6",
    no=CodingNode("P3"),
    yes=Q7,
    question_text="Is it viable to accomplish with reasonable resources for a developer?",
    help_text="Could the advice item be followed with an acceptable cost?. E.g., the advice would not take years to follow, or have cost out of line with the anticipated benefit.",
)
Q5 = CodingNode(
    label="Q5",
    no=CodingNode("P1"),
    yes=Q6,
    question_text="Does it describe or imply steps or explicit actions to take?",
    help_text="Does the advice suggest actionable technical steps (one or more) that suffice to follow the advice? It has sufficient detail to suggest a step/action to take. Actionable: Involving a known, unambiguous sequence of steps, whose means of execution is generally understood.",
)
Q10 = CodingNode(
    label="Q10",
    yes=CodingNode("N"),
    no=CodingNode("T'"),
    question_text="Is it a broad approach or security property?",
    help_text="Is the item a general way or general strategy, or a property that would improve security? A security property is a characteristic or attribute of a system related to security. E.g., an open design.",
)
Q9 = CodingNode(
    label="Q9",
    yes=CodingNode("P2"),
    no=Q10,
    question_text="Is it a general policy, general practice, or general procedure?",
    help_text="Is the item a security policy (general rule) to improve security, but is not explicit about what technical means is used? These are less actionable (akin to incompletely specified practices - definition in Q5), and are not technically explicit. A general policy often has more emphasis on what is (dis)allowed (or may be a general rule closely related to a desired outcome), rather than on how to achieve it.",
)
Q4 = CodingNode(
    label="Q4",
    yes=Q5,
    no=Q9,
    question_text="Does it suggest a technique, mechanism, software tool, or specific rule?",
    help_text="Is the item a method used in achieving/following the advice? E.g., encryption or replacing a password with black dots are techniques/mechanisms, but secure data or making the password unreadable are not. An example of a specific rule: no hard-coded credentials—this is a rule that is fairly specific as to its goal and would be followed like a practice, but not necessarily with actionable steps.",
)
Q3 = CodingNode(
    label="Q3",
    yes=CodingNode("T"),
    no=Q4,
    question_text="Is it focused more on a desired outcome than how to achieve it?",
    help_text="Is the advice a high-level outcome rather than some method (or meta-outcome) for how to achieve an outcome? E.g., data is secured in transit would be an outcome because it is a desired goal or state, whereas encrypt data in transit is not because it explains a method for achieving that outcome (in this case, encryption). Encryption may be considered a meta-outcome, as it is not meaningful to the end-user’s ultimate goal of protected data.",
)
Q2 = CodingNode(
    label="Q2",
    no=CodingNode("M2"),
    yes=Q3,
    question_text="Is it arguably helpful for CI/CD security?",
    help_text="Is the advice arguably useful for pursuing CI/CD security in some way? Does it seem like it will help improve security outcomes rather than processes unrelated to security?",
)
Q1b = CodingNode(
    label="Q1b",
    no=CodingNode("M1b"),
    yes=Q2,
    question_text="Is the item conveyed in clear language?",
    help_text="Does the advice make sense from a language perspective (e.g., it is a sentence that you can read and makes sense) and is unambiguous (i.e., you can tell what they are trying to convey from a language perspective, not technical)",
)
Q1a = CodingNode(
    label="Q1a",
    no=CodingNode("M1a"),
    yes=Q1b,
    question_text="Is the advice item focused?",
    help_text="Is the advice focused on one topic, whether it is a step to take, an outcome to achieve, or security principle? If the advice seems to have multiple topics being discussed or has multiple outcomes it wants an implementer to reach, this would be considered unfocused.",
)

CodingTree = Q1a
