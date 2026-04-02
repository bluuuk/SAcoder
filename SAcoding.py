from dataclasses import dataclass


class Tree:
    def __init__(self, label: str, yes=None, no=None):
        self.label = label
        self.yes = yes
        self.no = no

    def is_leaf(self) -> bool:
        return self.yes is None and self.no is None

    def next_step(self, answer: bool) -> "Tree":
        return self.yes if answer else self.no

    def question(self) -> "QuestionStep | None":
        if self.is_leaf():
            return None

        question_text, help_text = CodingQuestions[self.label]
        return QuestionStep(code=self.label, text=question_text, help_text=help_text)

    def classification_label(self) -> str:
        return CodingLabels.get(self.label, "Unknown Classification")

    def result(self, path: list[tuple["Tree", str]]) -> "ClassificationResult | None":
        if not self.is_leaf():
            return None

        return ClassificationResult(
            code=self.label,
            label=self.classification_label(),
            decision_path=[
                f"{node.question().text} -> {answer}"
                for node, answer in path
            ],
        )

CodingQuestions = {
    "Q1a":   [
        "Is the advice item focused?",
        "Is the advice focused on one topic, whether it is a step to take, an outcome to achieve, or security principle? If the advice seems to have multiple topics being discussed or has multiple outcomes it wants an implementer to reach, this would be considered unfocused."
        ],
    "Q1b":   [
        "Is the item conveyed in clear language?",
        "Does the advice make sense from a language perspective (e.g., it is a sentence that you can read and makes sense) and is unambiguous (i.e., you can tell what they are trying to convey from a language perspective, not technical)"
        ],
    "Q2":   [
        "Is it arguably helpful for CI/CD security?",
        "Is the advice arguably useful for pursuing CI/CD security in some way? Does it seem like it will help improve security outcomes rather than processes unrelated to security?"
        ],
    "Q3":   [
        "Is it focused more on a desired outcome than how to achieve it?",
        "Is the advice a high-level outcome rather than some method (or meta-outcome) for how to achieve an outcome? E.g., data is secured in transit would be an outcome because it is a desired goal or state, whereas encrypt data in transit is not because it explains a method for achieving that outcome (in this case, encryption). Encryption may be considered a meta-outcome, as it is not meaningful to the end-user’s ultimate goal of protected data."
        ],
    "Q4":   [
        "Does it suggest a technique, mechanism, software tool, or specific rule?",
        "Is the item a method used in achieving/following the advice? E.g., encryption or replacing a password with black dots are techniques/mechanisms, but secure data or making the password unreadable are not. An example of a specific rule: no hard-coded credentials—this is a rule that is fairly specific as to its goal and would be followed like a practice, but not necessarily with actionable steps."
        ],
    "Q5":   [
        "Does it describe or imply steps or explicit actions to take?",
        "Does the advice suggest actionable technical steps (one or more) that suffice to follow the advice? It has sufficient detail to suggest a step/action to take. Actionable: Involving a known, unambiguous sequence of steps, whose means of execution is generally understood."
        ],
    "Q6":   [
        "Is it viable to accomplish with reasonable resources for a developer?",
        "Could the advice item be followed with an acceptable cost?. E.g., the advice would not take years to follow, or have cost out of line with the anticipated benefit."
        ],
    "Q7":   [
        "Is it intended that the typical developer carry out this item?",
        "Does the item suggest that the typical developer can carrying out this practice?"
        ],
    "Q8":   [
        "Is it intended that a security expert carry out this item?",
        "Does following this advice require an expert understanding of security and security implementation in order to properly follow the advice? Someone following this advice item would have to be an expert in security to be able to understand it and successfully follow it, or be capable of extracting actionable steps from an otherwise non-actionable item based on their experience."
        ],
    "Q9":   [
        "Is it a general policy, general practice, or general procedure?",
        "Is the item a security policy (general rule) to improve security, but is not explicit about what technical means is used? These are less actionable (akin to incompletely specified practices - definition in Q5), and are not technically explicit. A general policy often has more emphasis on what is (dis)allowed (or may be a general rule closely related to a desired outcome), rather than on how to achieve it."
        ],
    "Q10":  [
        "Is it a broad approach or security property?",
        "Is the item a general way or general strategy, or a property that would improve security? A security property is a characteristic or attribute of a system related to security. E.g., an open design."
        ],
    "Q11":  [
        "Does it relate to a principle in the design?",
        "Some principles relate to the core design phase of the product/system rather than later lifecycle phases."
        ],
}

CodingLabels = {
    "M1a": "Unfocused",
    "M1b": "Unclear",
    "M2": "Not Security Related",
    "T": "Outcome",
    "T'": "Outcome",
    "P1": "Incompletely Specified Practice",
    "P2": "General Policy/Approach",
    "P3": "Infeasible Practice",
    "P4": "Security Expert",
    "P5": "IT Specialist",
    "P6": "Typical developer",
    "N": "Security Principle",
}


@dataclass(frozen=True)
class QuestionStep:
    code: str
    text: str
    help_text: str


@dataclass(frozen=True)
class ClassificationResult:
    code: str
    label: str
    decision_path: list[str]

Q8  = Tree(label="Q8",      no=Tree("P5"),      yes=Tree("P4"))    
Q7  = Tree(label="Q7",      yes=Tree("P6"),     no=Q8)    
Q6  = Tree(label="Q6",      no=Tree("P3"),      yes=Q7)   
Q5  = Tree(label="Q5",      no=Tree("P1"),      yes=Q6)  
Q10 = Tree(label="Q10",     yes=Tree("N"),      no=Tree("T'"))  
Q9  = Tree(label="Q9",      yes=Tree("P2"),     no=Q10)  
Q4  = Tree(label="Q4",      yes=Q5,             no=Q9)  
Q3  = Tree(label="Q3",      yes=Tree("T"),      no=Q4)  
Q2  = Tree(label="Q2",      no=Tree("M2"),      yes=Q3)  
Q1b = Tree(label="Q1b",     no=Tree("M1b"),     yes=Q2)  
Q1a = Tree(label="Q1a",     no=Tree("M1a"),     yes=Q1b)

CodingTree = Q1a 
