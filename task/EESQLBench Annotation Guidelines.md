# **EESQLBench Annotation Guidelines**

To ensure the quality, consistency, and reliability of efficiency-oriented annotations in EESQLBench, we design a structured, execution-driven annotation workflow covering annotator roles, annotation protocols, conflict resolution, and bias-mitigation mechanisms.

------

## **1. Annotator Roles**

We adopt a three-role annotation setup, following standard practices in empirical software engineering.

- Primary Annotators (2)

  Independently perform:

  - query optimization refinement,
  - optimization type annotation,
  - semantic consistency verification,
  - difficulty annotation.

- Adjudicator (1)
   Resolves disagreements between annotators and determines final labels.

- Expert Validators (shared pool)

  Perform final sanity checks on a subset of tasks to ensure:

  - semantic correctness,
  - optimization validity,
  - annotation consistency.

All annotators are **PhD-level researchers with SQL optimization experience**, satisfying the criteria below.

------

## **2. Annotator Qualification Criteria**

An annotator is considered a qualified expert only if they satisfy both the **eligibility criteria** and the **screening requirements** described below.

### **2.1 Eligibility Criteria**

- Background

  - PhD student (or equivalent) in Computer Science or related fields.

- SQL Optimization Expertise

  - Familiar with core optimization techniques, including:
    - predicate pushdown,
    - join reordering,
    - subquery elimination,
    - aggregation rewriting.

- Execution Plan Analysis

  - Able to interpret 

    EXPLAIN ANALYZE

     outputs and reason about:

    - operator-level cost,
    - scanned rows,
    - intermediate result sizes.

- Practical DBMS Experience

  - Hands-on experience with at least one relational DBMS (e.g., MySQL).

- Research or Engineering Experience

  - Prior experience in databases, query processing, or Text-to-SQL.

### **2.2 Screening and Verification Procedure**

To avoid relying solely on self-reported experience, we apply a lightweight but explicit screening procedure before formal annotation.

- Profile Check
  - We first verify each candidate’s academic background and prior experience in databases, SQL analysis, or Text-to-SQL-related research.
- Pilot Annotation Test
  - Each candidate is required to complete a pilot annotation exercise on a small set of development tasks not included in EESQLBench.
  - The pilot tasks cover:
    - semantic equivalence verification,
    - optimization type identification,
    - difficulty annotation.
- Execution-Plan Interpretation Test
  - Candidates must inspect query plans and explain the likely source of inefficiency, such as delayed filtering, redundant joins, or unnecessary aggregation.
  - This step is used to verify that the annotator can reason about query efficiency beyond surface-level SQL syntax.
- Consistency Check
  - Pilot annotations are compared against a reference annotation set prepared in advance.
  - We examine whether the candidate can make stable judgments on:
    - semantic equivalence,
    - optimization categories,
    - difficulty scores.
- Qualification Threshold
  - A candidate is accepted as an annotator only if their pilot annotations achieve high agreement with the reference annotations and show no systematic misunderstanding of optimization principles.

### **2.3 Calibration Before Formal Annotation**

Before the full annotation process, all qualified annotators participate in a calibration round using a shared set of example tasks. The goal is to ensure that all annotators apply the same standards when:

- identifying optimization types,
- comparing semantic equivalence,
- assigning difficulty scores.

Disagreement cases from the calibration round are discussed and incorporated into the final annotation guideline. This step helps reduce annotation drift and improves inter-annotator consistency during the main study.

------

## **3. Annotation Scope and Types**

Each task consists of:

- Original SQL (inefficient)
- Optimized SQL (canonical)
- Natural language question
- Database context

We annotate three key aspects:

------

### **3.1 Semantic Consistency**

For each original–optimized query pair, we verify whether the two queries are **semantically consistent in practice**, rather than relying on a single execution match on one fixed database instance.

Each query pair is assigned one of the following labels:

- **Consistent**: the two queries produce identical results across all verification settings and pass manual inspection for intent preservation.
- **Inconsistent**: the two queries produce mismatched results in any verification setting, fail to execute, or exhibit structural changes that alter the intended semantics.

**Verification Protocol.**
 To reduce the risk of accidental result agreement on a single data instance, we adopt a multi-step verification procedure:

- **Execution under identical conditions**
   Execute both queries on the same database under identical system settings.
- **Result-set comparison**
   Compare the returned results exactly, taking into account duplicates, NULL values, and ordering when `ORDER BY` is semantically required.
- **Repeated verification across perturbed instances**
   Re-check the query pair on multiple data instances derived from the same schema, including lightly perturbed instances produced by controlled data augmentation or value resampling. This helps reduce false equivalence caused by coincidental data distributions.
- **Manual semantic inspection**
   Annotators manually inspect whether the optimized query preserves the intent of the original query, especially for transformations involving subqueries, aggregation scopes, join predicates, or filter placement.

------

### **3.2 Optimization Type Annotation**

Annotate the primary optimization techniques applied, including:

- Predicate Pushdown
- Join Reordering
- Subquery Elimination
- Aggregation Rewriting
- Redundant Join Removal
- Access Path Optimization

Each optimization must be:

- **Explicitly identifiable in the query structure**, and
- **Justified by execution plan improvement**.

------

### **3.3 Task Difficulty Annotation**

- We evaluate task difficulty across 3 dimensions, each scored **0–2**, with the total score determining the final annotated difficulty level.

  The mapping between the difficulty level and the total score is as follows:

  | Difficulty Label | Total Score Range |
  | :--------------: | ----------------- |
  |    **Simple**    | 0 ~ 1             |
  |    **Medium**    | 2 ~ 3             |
  |     **Hard**     | 4 ~ 6             |

  **1 Schema Complexity**

  This dimension assesses the schema complexity of the database environment associated with each task.

  <table border="1" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
    <thead>
      <tr style="background-color: #f2f2f2; text-align: left;">
        <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Score</th>
        <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Criteria</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">0</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>&le; 2 tables</li>
            <li>Straightforward foreign keys (if any)</li>
            <li>No many-to-many patterns</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">1</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>3 ~ 4 tables or multiple join paths</li>
            <li>Foreign-key chains or mild schema ambiguity</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">2</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>&ge; 5 tables or dense join graph</li>
            <li>Multiple alternative join paths, bridge tables, or complex key relationships</li>
          </ul>
        </td>
      </tr>
    </tbody>
  </table>

  **2 Question Complexity**

  This dimension assesses the linguistic complexity and logical depth of the natural language question.

  <table border="1" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
    <thead>
      <tr style="background-color: #f2f2f2; text-align: left;">
        <th style="padding: 10px; border: 1px solid #ddd; width: 20%; text-align: center;">Score</th>
        <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Criteria</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">0</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>Single clear intent with explicit constraints</li>
            <li>&le; 1 predicate or trivial conditions</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">1</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>2 ~ 3 predicates or implicit constraints</li>
            <li>Basic linguistic reasoning (e.g., temporal range filter like "within the last year", quantitative qualifiers like "top 5")</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">2</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>Multi-hop reasoning, implicit grouping logic, or compound relational constraints</li>
            <li>Complex semantic patterns (e.g., comparative reasoning like "only if" logic, or nested exclusion patterns like "except")</li>
          </ul>
        </td>
      </tr>
    </tbody>
  </table>

  **3 SQL Complexity**

  This dimension assesses the structural intricacy of the target SQL statement.

  <table border="1" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
    <thead>
      <tr style="background-color: #f2f2f2; text-align: left;">
        <th style="padding: 10px; border: 1px solid #ddd; width: 20%; text-align: center;">Score</th>
        <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">Criteria</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">0</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>Single <code>SELECT</code> block with basic filters and joins</li>
            <li>No subqueries, Common Table Expressions (CTEs), and window functions</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">1</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>Aggregation logic with <code>GROUP BY</code> or <code>HAVING</code> clauses</li>
            <li>Includes 1 subqueries, derived tables, or <code>UNION</code> operations</li>
            <li>Moderate join chain: involves 3～4 tables and 2～3 joins</li>
          </ul>
        </td>
      </tr>
      <tr>
        <td style="padding: 10px; border: 1px solid #ddd; text-align: center; font-weight: bold;">2</td>
        <td style="padding: 10px; border: 1px solid #ddd;">
          <ul style="margin: 0; padding-left: 20px;">
            <li>Multiple subqueries, multi-level nesting, or multiple CTEs</li>
            <li>Advanced feature (e.g., window functions, complex set operations)</li>
            <li>Multi-stage aggregation logic</li>
            <li>Heavy join chain: involves &ge; 5 tables and &ge; 4 joins</li>
          </ul>
        </td>
      </tr>
    </tbody>
  </table>

  

------

## **4. Annotation Workflow**

1. Load database schema and data;
2. Execute original SQL and analyze execution plan;
3. Generate optimized query (via rewriting + refinement);
4. Verify semantic equivalence;
5. Compare execution cost (Total Scanned Rows);
6. Annotate optimization types;
7. Assign difficulty labels;
8. Submit for independent review.

------

## **5. Independence and Conflict Resolution**

To ensure objectivity:

- Two annotators independently annotate each task:
  - no communication,
  - no shared intermediate results.
- Disagreements are:
  - reviewed by the adjudicator,
  - resolved based on:
    - execution results,
    - query plans,
    - guideline consistency.
- All conflicts must be resolved before final inclusion.

------

## **6. Bias-Mitigation Protocols**

We adopt multiple strategies to reduce bias:

------

### **6.1 Execution-Based Validation (Core Mechanism)**

All annotations must satisfy:

- identical execution results (semantic correctness),
- strictly lower cost for optimized queries.

This ensures **objective, data-driven decisions** instead of subjective judgment.

------

### **6.2 Standardized Annotation Guidelines**

- All annotators follow a unified guideline;
- Optimization categories are predefined;
- Difficulty scoring follows explicit rules.

------

### **6.3 Role Separation**

- Query generation, optimization, and annotation are conducted in separate stages;
- Annotators do not participate in earlier pipeline stages.

------

### **6.4 Independent Double Annotation**

- Each task is annotated twice independently;
- Prevents anchoring and confirmation bias.

------

### **6.5 Inter-Annotator Agreement**

- Measured using **Cohen’s κ (κ = 0.92)**;
- Indicates high consistency and reliability.

------

### **6.6 Disagreement Auditing**

- All disagreements are logged;
- Patterns are used to refine guidelines;
- Ambiguous cases are revised or removed.

------

## **7. Quality Assurance**

### **7.1 Semantic Verification**

- Execution results must match exactly.

### **7.2 Efficiency Verification**

- Optimized query must consistently reduce cost.

### **7.3 Annotation Validation**

- Optimization types must align with actual transformations.

### **7.4 Manual Review**

- Experts review edge cases and correct errors.