import type { Task, TaskStatus } from "../types";
import { StatusPill } from "./StatusPill";

const columns: TaskStatus[] = ["backlog", "assigned", "working", "waiting_on_paths", "needs_review", "blocked", "done"];

export function TaskBoard({ tasks, onStartTask }: { tasks: Task[]; onStartTask: (taskId: number) => void }) {
  return (
    <div className="task-board">
      {columns.map((column) => {
        const items = tasks.filter((task) => task.status === column);
        return (
          <section key={column} className="task-column">
            <div className="task-column__header">
              <h3>{column.replace("_", " ")}</h3>
              <span>{items.length}</span>
            </div>
            <div className="task-column__items">
              {items.map((task) => (
                <article key={task.id} className="task-card">
                  <div className="task-card__top">
                    <span className="task-card__id">Task #{task.id}</span>
                    <StatusPill status={task.status} />
                  </div>
                  <h4>{task.title}</h4>
                  <p>{task.goal}</p>
                  <p>{task.milestone ?? "Unassigned milestone"}</p>
                  <div className="task-card__paths">
                    <strong>Allowed:</strong> {task.allowed_paths_json.join(", ")}
                  </div>
                  {task.waiting_reason ? (
                    <div className="task-card__paths">
                      <strong>Waiting:</strong> {task.waiting_reason}
                    </div>
                  ) : null}
                  <div className="task-card__paths">
                    <strong>Complexity:</strong> {task.estimated_complexity}
                  </div>
                  {task.status === "backlog" || task.status === "assigned" ? (
                    <button className="button-ghost" onClick={() => onStartTask(task.id)}>
                      Start task
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
