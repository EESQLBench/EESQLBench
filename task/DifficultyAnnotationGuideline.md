# Difficulty Annotation Guideline

We evaluate task difficulty across 3 dimensions, each scored **0–2**, with the total score determining the final annotated difficulty level.

The mapping between the difficulty level and the total score is as follows:

| Difficulty Label | Total Score Range |
| :---: | --- |
| **Simple** | 0 ~ 1 | 
| **Medium** | 2 ~ 3 |
| **Hard**   | 4 ~ 6 | 


## 1 Schema Complexity

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

## 2 Question Complexity

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

## 3 SQL Complexity

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

